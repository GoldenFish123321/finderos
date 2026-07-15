"""collector.py — 瞭望采集服务

- 通过 RequestHeaders + URL 模板 + 关键词 + 分页 拼装并发起 HTTP 请求
- 内置多种 parser [baidu_news / sogou_news / generic]
- 仅依赖 Python 标准库 + 正则: 不引入第三方 HTML 解析器 (保持零依赖)
"""
from __future__ import annotations

import gzip
import io
import logging
import re
import ssl
import threading
import time
import urllib.parse
import urllib.request
import zlib
from html import unescape
from http.cookiejar import CookieJar
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# 全局 CookieJar — 百度验证码需要先访问首页获取 BAIDUID 等 cookie
_global_cookie_jar: Optional[CookieJar] = None
_global_cookie_lock = threading.Lock()
_global_ssl_ctx = ssl.create_default_context()
# 百度服务器不支持 TLS 1.3（返回 TLSV1_ALERT_PROTOCOL_VERSION），
# 且 Python 3.13 + OpenSSL 3.0 在 TLS 1.3→1.2 降级时有缺陷会导致握手超时，
# 因此显式限制最高 TLS 版本为 1.2（与 Windows Schannel / curl 行为一致）。
_global_ssl_ctx.maximum_version = ssl.TLSVersion.TLSv1_2


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """禁止 HTTP 重定向跟随，防止 SSRF 绕过（重定向到内网地址）。"""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # 不跟随任何重定向

    # 将 3xx 响应视为正常响应返回，而非抛出异常
    http_error_301 = http_error_302 = http_error_303 = http_error_307 = http_error_308 = (
        lambda self, req, fp, code, msg, hdrs: fp
    )


# 预构建不跟随重定向的 opener（线程安全，可复用）
_no_redirect_opener = urllib.request.build_opener(
    _NoRedirectHandler(),
    urllib.request.HTTPSHandler(context=_global_ssl_ctx),
)

# 预定义的 Chrome 138 TLS 指纹 header
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


def _decompress(data: bytes, encoding: str) -> bytes:
    """解压 HTTP 响应体（gzip / deflate / br raw）。

    注意: Brotli (br) 需要安装 brotli 或 brotlipy 包；
    未安装或解压失败时返回原始数据（与 gzip/deflate 行为一致），避免数据静默丢失。
    """
    if not data:
        return data
    enc = (encoding or "").lower()
    if "gzip" in enc:
        try:
            return gzip.decompress(data)
        except Exception:
            pass
    if "deflate" in enc:
        try:
            return zlib.decompress(data)
        except Exception:
            try:
                return zlib.decompress(data, -15)
            except Exception:
                pass
    if "br" in enc:
        try:
            import brotli
            return brotli.decompress(data)
        except ImportError:
            logger.error("响应使用 Brotli 压缩，但 brotli 包未安装，无法解压，将使用原始数据。请执行: pip install brotli")
            return data
        except Exception as e:
            logger.error(f"Brotli 解压失败: {e}，将使用原始数据")
            return data
    return data


def parse_baidu_news(html: str) -> List[Dict]:
    """从百度新闻搜索结果 HTML 解析新闻条目。

    百度新闻结果通常包含在 class 含 "result" 的 div 容器中。
    每条新闻包含：标题链接（h3 > a）、摘要（c-abstract）、来源（c-author）。
    """
    results: List[Dict] = []
    if not html or len(html) < 1000:
        return results

    # 按 class 含 "result" 的 div 切分 HTML
    blocks = re.split(r'<div[^>]*class="[^"]*result[^"]*"[^>]*>', html)
    if len(blocks) <= 1:
        blocks = re.split(r"<h3[^>]*>", html)

    for block in blocks[1:]:
        title = ""
        link = ""
        summary = ""
        source_name = "百度新闻"

        # 提取标题和链接
        tm = re.search(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', block, re.DOTALL)
        if not tm:
            tm = re.search(r'href="([^"]*)"[^>]*>(.*?)</a>', block, re.DOTALL)
        if tm:
            link = tm.group(1)
            raw = tm.group(2)
            title = re.sub(r"<[^>]+>", "", raw).strip()
            title = unescape(title)

        if not title or len(title) < 4:
            continue
        if any(s in title.lower() for s in ["首页", "下一页", "百度", "登录", "注册", "设置"]):
            continue

        # 提取摘要
        sm = re.search(
            r'<(?:span|div|p|em)[^>]*class="[^"]*(?:abstract|summary|content|desc)[^"]*"[^>]*>(.*?)</(?:span|div|p|em)>',
            block, re.DOTALL,
        )
        if not sm:
            sm = re.search(
                r"<(?:span|div|p)[^>]*>(.{20,200}?)</(?:span|div|p)>",
                block, re.DOTALL,
            )
        if sm:
            summary = re.sub(r"<[^>]+>", "", sm.group(1)).strip()
            summary = unescape(summary)
            if len(summary) > 200:
                summary = summary[:200] + "..."

        # 提取来源
        src_m = re.search(
            r'<(?:span|div|a)[^>]*class="[^"]*(?:source|author|site|c-author)[^"]*"[^>]*>(.*?)</(?:span|div|a)>',
            block, re.DOTALL,
        )
        if src_m:
            src = re.sub(r"<[^>]+>", "", src_m.group(1)).strip()
            if src and len(src) < 50:
                source_name = unescape(src)

        # 处理相对链接
        if link and not link.startswith("http"):
            if link.startswith("//"):
                link = "https:" + link
            elif link.startswith("/"):
                link = "https://www.baidu.com" + link

        results.append({
            "title": title,
            "link": link,
            "summary": summary,
            "source_name": source_name,
        })

        if len(results) >= 20:
            break

    return results


def parse_sogou_news(html: str) -> List[Dict]:
    """从搜狗新闻搜索结果 HTML 解析新闻条目。"""
    results: List[Dict] = []
    if not html or len(html) < 1000:
        return results

    # 搜狗新闻结果在 class=\"news-item\" 或 class=\"vrwrap\" 等容器中
    blocks = re.split(r'<(?:div|li)[^>]*class="[^"]*(?:news-item|vrwrap|rb)[^"]*"[^>]*>', html)
    if len(blocks) <= 1:
        blocks = re.split(r"<h3[^>]*>", html)

    for block in blocks[1:]:
        title = ""
        link = ""
        summary = ""

        tm = re.search(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', block, re.DOTALL)
        if not tm:
            continue
        link = tm.group(1)
        raw = tm.group(2)
        title = re.sub(r"<[^>]+>", "", raw).strip()
        title = unescape(title)

        if not title or len(title) < 4:
            continue
        if any(s in title for s in ["下一页", "首页", "登录"]):
            continue

        # 摘要
        sm = re.search(r'<(?:p|span|div)[^>]*class="[^"]*(?:abstract|summary|desc|info|txt)[^"]*"[^>]*>(.*?)</(?:p|span|div)>', block, re.DOTALL)
        if not sm:
            sm = re.search(r"<(?:p|span|div)[^>]*>(.{20,200}?)</(?:p|span|div)>", block, re.DOTALL)
        if sm:
            summary = re.sub(r"<[^>]+>", "", sm.group(1)).strip()
            summary = unescape(summary)
            if len(summary) > 200:
                summary = summary[:200] + "..."

        if link and not link.startswith("http"):
            if link.startswith("//"):
                link = "https:" + link

        results.append({
            "title": title,
            "link": link,
            "summary": summary,
            "source_name": "搜狗新闻",
        })

        if len(results) >= 20:
            break

    return results


def generic_parse(html: str) -> List[Dict]:
    """通用解析器：提取页面中所有 h3/h2 标题链接。"""
    results = []
    titles = re.findall(
        r'<(?:h[23])[^>]*>\s*<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
        html, re.DOTALL,
    )
    for link, raw in titles[:20]:
        title = re.sub(r"<[^>]+>", "", raw).strip()
        title = unescape(title)
        if len(title) >= 4:
            results.append({"title": title, "link": link, "summary": "", "source_name": "未知来源"})
    return results


PARSERS = {
    "baidu_news": parse_baidu_news,
    "sogou_news": parse_sogou_news,
    "generic": generic_parse,
}


def _ensure_baidu_cookies():
    """确保全局 CookieJar 中有百度的 BAIDUID cookie（绕过验证码）。

    设计原则：
    - HTTP 请求在锁外执行，避免阻塞其他线程（最长可阻塞 51s）。
    - 仅在读写 _global_cookie_jar 时短暂持锁，保证线程安全。
    - 首次调用时多个线程可能并发请求百度首页，但这是可接受的
      （仅发生在冷启动时，且远优于所有线程被锁阻塞 51s）。
    - 内建重试机制（最多 3 次，指数退避），每次重试使用全新 SSL 上下文，
      应对间歇性 SSL 握手超时。
    """
    global _global_cookie_jar
    if _global_cookie_jar is not None:
        return

    # ── HTTP 请求在锁外执行（不阻塞其他线程） ──
    max_retries = 3
    last_error = None
    cj = None

    for attempt in range(max_retries):
        cj = CookieJar()
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(cj),
            urllib.request.HTTPSHandler(context=_global_ssl_ctx),
        )
        try:
            req = urllib.request.Request("https://www.baidu.com/", headers=dict(_BASE_HEADERS))
            resp = opener.open(req, timeout=15)
            try:
                resp.read()
            finally:
                resp.close()
            break  # 成功，跳出重试循环
        except Exception as e:
            last_error = e
            cj = None
            if attempt < max_retries - 1:
                wait_sec = (attempt + 1) * 2  # 2s, 4s 退避
                logger.debug(f"百度 Cookie 预热第 {attempt + 1} 次失败，{wait_sec}s 后重试: {e}")
                time.sleep(wait_sec)

    # ── 仅在写全局变量时短暂持锁 ──
    with _global_cookie_lock:
        # 双重检查：可能另一个线程已经在我们请求期间完成了初始化
        if _global_cookie_jar is not None:
            return
        if cj is not None:
            cookie_count = len(list(cj))
            _global_cookie_jar = cj
            logger.info(f"百度 Cookie 预热成功: {cookie_count} 个")
        else:
            logger.warning(f"百度 Cookie 预热失败（{max_retries} 次重试后）: {last_error}")
            # 不将 _global_cookie_jar 设为 None（已经是 None），
            # 下次调用会重试。不做持久化标记以避免死锁恢复问题。


def _clean_html(html: str) -> str:
    """清洗 HTML 内容，移除 <script> / <style> 标签及其内容。

    防止采集结果中嵌入可执行脚本或样式污染。
    借鉴陈子墨项目的 HTML 清洗实践。
    """
    if not html:
        return html
    # 移除 script 和 style 标签及其内容
    cleaned = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r'<style[^>]*>.*?</style>', '', cleaned, flags=re.DOTALL | re.IGNORECASE)
    # 移除 HTML 注释
    cleaned = re.sub(r'<!--.*?-->', '', cleaned, flags=re.DOTALL)
    return cleaned


def fetch_and_parse(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    parser: str = "baidu_news",
    timeout: int = 15,
) -> Tuple[int, int, str, List[Dict]]:
    """发起 HTTP GET → 解压 → 按 parser 解析 → 返回 (状态码, 大小, 原文, 新闻列表)。

    百度 URL 会自动先访问首页获取验证 Cookie。
    内置 SSRF 防护：拒绝内网/回环地址。
    """
    # SSRF 防护校验
    from app.utils.security import validate_url_safe
    is_safe, reason, _ = validate_url_safe(url)
    if not is_safe:
        logger.warning(f"SSRF 拦截: {reason} — {url[:100]}")
        return 0, 0, f"SSRF Blocked: {reason}", []

    if headers is None:
        headers = dict(_BASE_HEADERS)
    else:
        # 合并用户 headers 到基础 headers
        merged = dict(_BASE_HEADERS)
        merged.update(headers)
        headers = merged

    # 百度 URL 需要先获取 Cookie（线程安全）
    if "baidu.com" in url:
        _ensure_baidu_cookies()

    try:
        # 局部引用避免全局变量在检查和使用之间被修改
        cookie_jar = _global_cookie_jar
        if cookie_jar is not None and "baidu.com" in url:
            # 百度需 Cookie，但仍禁止重定向（SSRF 防护）
            opener = urllib.request.build_opener(
                _NoRedirectHandler(),
                urllib.request.HTTPCookieProcessor(cookie_jar),
                urllib.request.HTTPSHandler(context=_global_ssl_ctx),
            )
            req = urllib.request.Request(url, headers=headers)
            resp = opener.open(req, timeout=timeout)
        else:
            req = urllib.request.Request(url, headers=headers)
            resp = _no_redirect_opener.open(req, timeout=timeout)

        try:
            raw = resp.read()
            encoding = resp.headers.get("Content-Encoding", "")
            status = resp.status
        finally:
            resp.close()
    except Exception as e:
        return 0, 0, f"Error: {e}", []

    data = _decompress(raw, encoding)
    try:
        text = data.decode("utf-8", errors="replace")
    except Exception:
        text = data.decode("gbk", errors="replace")

    size = len(raw)  # 使用原始字节数作为响应大小（而非字符数）
    # 清洗 HTML（移除 script/style 等潜在危险标签）
    safe_text = _clean_html(text)
    parse_fn = PARSERS.get(parser, generic_parse)
    try:
        news = parse_fn(safe_text)
    except Exception as e:
        logger.warning(f"解析器 {parser} 失败: {e}")
        news = []

    return status, size, safe_text, news
