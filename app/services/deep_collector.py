"""
deep_collector.py — 深度采集服务

对数据仓库中已保存的链接进行深度内容抓取：
- 访问目标 URL，获取完整 HTML
- 提取文章正文（标题、段落、图片等结构化内容）
- 将提取的内容回存到数据仓库

仅依赖 Python 标准库 + 正则，保持项目 "零依赖" 设计理念。
"""
from __future__ import annotations

import gzip
import io
import logging
import re
import ssl
import urllib.request
import zlib
from html import unescape
from typing import Dict, Optional, Tuple
from urllib.parse import urljoin, urlparse

from app.utils.security import validate_url_safe

# 尝试导入 crawl4ai（可选依赖，增强正文提取）
try:
    import crawl4ai  # noqa: F401
    _HAS_CRAWL4AI = True
except ImportError:
    _HAS_CRAWL4AI = False

logger = logging.getLogger(__name__)
from app.utils.safe_http import SafeHttpError, safe_http_request

# 复用 collector 的 SSL 上下文和请求头
_ssl_ctx = ssl.create_default_context()
# 百度等国内站点不支持 TLS 1.3，且 Python 3.13 + OpenSSL 3.0 降级有缺陷，
# 显式限制最高 TLS 版本为 1.2。
_ssl_ctx.maximum_version = ssl.TLSVersion.TLSv1_2


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """禁止 HTTP 重定向跟随，防止 SSRF 绕过（重定向到内网地址）。"""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

    http_error_301 = http_error_302 = http_error_303 = http_error_307 = http_error_308 = (
        lambda self, req, fp, code, msg, hdrs: fp
    )


# 预构建不跟随重定向的 opener
_no_redirect_opener = urllib.request.build_opener(
    _NoRedirectHandler(),
    urllib.request.HTTPSHandler(context=_ssl_ctx),
)

_BASE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/138.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Accept-Encoding": "gzip, deflate",
}

# ── 文章正文提取 ──────────────────────────────────────────────

# 常见正文容器标签/类名模式
_CONTENT_PATTERNS = [
    # 按优先级排序
    r'<(?:article|main)[^>]*>(.*?)</(?:article|main)>',
    r'<div[^>]*class="[^"]*(?:article-content|article_content|post-content|post_content|'
    r'content-body|content_body|entry-content|entry_content|article-body|article_body|'
    r'news-content|news_content|detail-content|detail_content|'
    r'rich_media_content|js_content)[^"]*"[^>]*>(.*?)</div>',
    r'<div[^>]*id="[^"]*(?:article|content|post|entry|main|news|detail)[^"]*"[^>]*>(.*?)</div>',
    r'<div[^>]*class="[^"]*(?:article|content|post|entry|main|news|detail)[^"]*"[^>]*>(.*?)</div>',
]

# 需要移除的无关标签
_REMOVE_TAGS_PATTERN = re.compile(
    r'<(?:script|style|iframe|nav|footer|header|aside|noscript|'
    r'form|input|button|select|textarea|svg|canvas|'
    r'video|audio|source|embed|object)[^>]*>.*?</(?:script|style|iframe|nav|footer|'
    r'header|aside|noscript|form|button|select|textarea|svg|canvas|'
    r'video|audio|source|embed|object)>',
    re.DOTALL | re.IGNORECASE,
)

# 自闭合标签
_REMOVE_SELF_CLOSING = re.compile(
    r'<(?:script|style|iframe|link|meta|img|br|hr|input)[^>]*/?>',
    re.IGNORECASE,
)

# 注释
_REMOVE_COMMENTS = re.compile(r'<!--.*?-->', re.DOTALL)


def _decompress(data: bytes, encoding: str) -> bytes:
    """解压 HTTP 响应体。

    Brotli (br) 未安装或解压失败时返回原始数据（与 gzip/deflate 行为一致），避免数据静默丢失。
    """
    if not data:
        return data
    enc = (encoding or "").lower()
    if "gzip" in enc:
        try:
            obj = zlib.decompressobj(16 + zlib.MAX_WBITS)
            result = obj.decompress(data, 30 * 1024 * 1024 + 1)
            if len(result) > 30 * 1024 * 1024 or obj.unconsumed_tail:
                raise ValueError("解压后响应超过大小限制")
            return result
        except Exception as exc:
            logger.warning("gzip 响应解压失败，保留原始数据: %s", exc)
    if "deflate" in enc:
        try:
            obj = zlib.decompressobj()
            result = obj.decompress(data, 30 * 1024 * 1024 + 1)
            if len(result) > 30 * 1024 * 1024 or obj.unconsumed_tail:
                raise ValueError("解压后响应超过大小限制")
            return result
        except Exception as exc:
            logger.warning("zlib deflate 解压失败，尝试 raw deflate: %s", exc)
            try:
                obj = zlib.decompressobj(-15)
                result = obj.decompress(data, 30 * 1024 * 1024 + 1)
                if len(result) > 30 * 1024 * 1024 or obj.unconsumed_tail:
                    raise ValueError("解压后响应超过大小限制")
                return result
            except Exception as raw_exc:
                logger.warning("raw deflate 解压失败，保留原始数据: %s", raw_exc)
    if "br" in enc:
        try:
            import brotli
        except ImportError:
            logger.debug("Brotli 未安装，跳过 br 解压")
            return data
        decoder = brotli.Decompressor()
        result = bytearray()
        try:
            for offset in range(len(data)):
                result.extend(decoder.process(data[offset:offset + 1]))
                if len(result) > 30 * 1024 * 1024:
                    raise ValueError("解压后响应超过大小限制")
            if not decoder.is_finished():
                raise ValueError("Brotli 响应不完整")
            return bytes(result)
        except brotli.error as e:
            logger.warning("Brotli 解压失败: %s", e)
            return data
    return data


def _extract_title(html: str) -> str:
    """从 HTML 中提取标题。"""
    # 优先 og:title
    m = re.search(r'<meta[^>]*property="og:title"[^>]*content="([^"]*)"', html, re.IGNORECASE)
    if m:
        return unescape(m.group(1).strip())
    # 其次 <title>
    m = re.search(r'<title[^>]*>(.*?)</title>', html, re.DOTALL | re.IGNORECASE)
    if m:
        title = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        # 去除站点名后缀（通常用 | - _ 分隔）
        for sep in ['|', '-', '_', '—']:
            if sep in title:
                parts = [p.strip() for p in title.rsplit(sep, 1)]
                if len(parts[1]) < len(parts[0]) and len(parts[1]) > 2:
                    title = parts[0]
                    break
        return unescape(title)
    # 最后 h1
    m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL | re.IGNORECASE)
    if m:
        return unescape(re.sub(r'<[^>]+>', '', m.group(1)).strip())
    return ""


def _extract_text_content(html: str, base_url: str = "") -> str:
    """从 HTML 中提取正文纯文本。

    策略：
    1. 移除 script/style/nav/footer 等无关标签
    2. 尝试匹配已知正文容器
    3. 如无匹配，使用全页面 body 内容
    4. 提取所有文本节点，合并为纯净文本
    """
    if not html:
        return ""

    # 预清理：移除注释、script、style 等
    cleaned = _REMOVE_COMMENTS.sub("", html)
    cleaned = _REMOVE_TAGS_PATTERN.sub("", cleaned)

    # 尝试匹配正文容器
    content_html = ""
    for pattern in _CONTENT_PATTERNS:
        m = re.search(pattern, cleaned, re.DOTALL | re.IGNORECASE)
        if m:
            # 所有 _CONTENT_PATTERNS 均只有1个捕获组，直接取 group(1)
            content_html = m.group(1)
            if len(content_html) > 500:
                break

    if not content_html or len(content_html) < 200:
        # 回退：使用 body 内容
        m = re.search(r'<body[^>]*>(.*?)</body>', cleaned, re.DOTALL | re.IGNORECASE)
        if m:
            content_html = m.group(1)
        else:
            content_html = cleaned

    # 提取段落文本
    paragraphs = []
    # 按 <p> <div> <br> 等分段
    # 先提取所有 <p> 段落
    for m in re.finditer(r'<p[^>]*>(.*?)</p>', content_html, re.DOTALL | re.IGNORECASE):
        text = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        text = unescape(text)
        # 过滤太短或明显非正文的段落
        if len(text) >= 15 and not re.match(r'^(版权所有|免责声明|广告|相关阅读|推荐阅读|分享|举报|评论)', text):
            paragraphs.append(text)

    # 如果没有 <p> 段落，按 <div>/<br> 分段
    if not paragraphs:
        # 清理所有标签
        text = re.sub(r'<br\s*/?>', '\n', content_html, flags=re.IGNORECASE)
        text = re.sub(r'<[^>]+>', '', text)
        text = unescape(text)
        # 按空行分段
        for para in re.split(r'\n\s*\n', text):
            para = para.strip()
            if len(para) >= 15:
                paragraphs.append(para)

    # 合并段落
    result = "\n\n".join(paragraphs)
    # 截断过长内容（保留前 50000 字符）
    if len(result) > 50000:
        result = result[:50000] + "\n\n... (内容过长，已截断)"

    return result


def deep_fetch(url: str, timeout: int = 30) -> Tuple[int, str, str, str]:
    """
    深度抓取指定 URL，提取标题和正文。

    返回: (状态码, 标题, 正文纯文本, 错误消息)
    - 成功: (200, title, content, "")
    - 失败: (status_code, "", "", error_message)
    """
    if not url:
        return 0, "", "", "URL 为空"

    # crawl4ai 集成待实现（库已安装但暂未对接），直接使用自研解析方案
    if _HAS_CRAWL4AI:
        logger.debug("crawl4ai 已安装但集成代码待实现，使用自研方案")

    # SSRF 校验
    is_safe, reason, _ = validate_url_safe(url)
    if not is_safe:
        logger.warning(f"深度采集 SSRF 拦截: {url} — {reason}")
        return 0, "", "", f"安全校验失败: {reason}"

    try:
        response = safe_http_request(
            url, headers=_BASE_HEADERS, timeout=timeout, max_bytes=10 * 1024 * 1024
        )
        status = response.status
        if 300 <= status < 400:
            return status, "", "", "采集目标不允许重定向"
        encoding = response.headers.get("Content-Encoding", "")
        raw = response.body

        # 解压
        data = _decompress(raw, encoding)
        if len(data) > 30 * 1024 * 1024:
            return 0, "", "", "解压后响应超过大小限制"

        # 检测字符编码（两阶段：strict 试探 + replace 容错解码）
        html = ""
        detected_charset = None
        for charset_try in ["utf-8", "gbk", "gb2312", "gb18030", "latin-1"]:
            try:
                data.decode(charset_try, errors="strict")  # 试探：抛异常则表示不匹配
                detected_charset = charset_try
                break
            except (UnicodeDecodeError, LookupError):
                continue
        if detected_charset:
            html = data.decode(detected_charset, errors="replace")
        else:
            html = data.decode("utf-8", errors="replace")

        if not html or len(html) < 500:
            return status, "", "", "页面内容过短，可能为验证页面"

        title = _extract_title(html)
        content = _extract_text_content(html, url)

        if not content and not title:
            return status, "", "", "未能提取到有效正文内容"
        return status, title, content, ""

    except SafeHttpError as e:
        logger.warning("Deep fetch blocked: %s", e)
        return 0, "", "", "目标地址或响应不符合安全策略"
    except urllib.error.HTTPError as e:
        logger.warning(f"Deep fetch HTTP error for {url}: {e.code} {e.reason}")
        return e.code, "", "", f"HTTP {e.code}: 请求失败"
    except urllib.error.URLError as e:
        logger.warning(f"Deep fetch URL error for {url}: {e.reason}")
        return 0, "", "", "网络请求失败，请稍后重试"
    except ssl.SSLError as e:
        logger.warning(f"Deep fetch SSL error for {url}: {e}")
        return 0, "", "", "SSL 连接失败"
    except Exception as e:
        logger.error(f"Deep fetch unexpected error for {url}: {e}")
        return 0, "", "", "采集过程发生异常，请稍后重试"


def deep_fetch_and_save(warehouse_id: int, link: str) -> Tuple[bool, str]:
    """
    对指定数据仓库记录执行深度采集并保存。

    返回: (成功, 消息)
    """
    if not link:
        return False, "该记录没有可采集的链接"

    status, title, content, error = deep_fetch(link)

    if error:
        return False, f"深度采集失败: {error}"

    from app.models.data_warehouse import DataWarehouseRepository

    # 合并采集结果
    full_content = ""
    if title:
        full_content += f"【标题】{title}\n\n"
    if content:
        full_content += content

    content_size = len(full_content.encode("utf-8"))
    ok = DataWarehouseRepository.mark_deep_collected(
        warehouse_id, content=full_content, content_size=content_size
    )

    if ok:
        size_kb = content_size / 1024
        return True, f"深度采集完成（提取 {size_kb:.1f} KB 正文内容）"
    else:
        return False, "保存深度采集内容失败"
