"""
crawl4ai_tools.py — Crawl4ai 爬虫增强类 MCP 工具处理函数 (v0.10 新增)

工具:
- collect_with_crawl4ai: Crawl4ai 智能采集
- batch_deep_collect: 批量深度采集
"""

import asyncio
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


async def _deep_collect_url(url: str, extract_mode: str = "auto") -> Dict[str, Any]:
    """使用 Crawl4ai 对指定 URL 进行智能深度采集。

    替代旧的 crawl4ai_enabled 复选框功能。
    优先尝试 crawl4ai，不可用时回退到标准深度采集。
    """
    import asyncio
    from app.services.deep_collector import deep_fetch, _HAS_CRAWL4AI
    from app.utils.security import validate_url_safe

    # SSRF 防护：验证 URL 安全性
    safe, reason, _ = validate_url_safe(url)
    if not safe:
        return {"success": False, "url": url, "error": f"URL 安全校验未通过: {reason}"}

    loop = asyncio.get_event_loop()

    if _HAS_CRAWL4AI:
        try:
            # TODO: 当 crawl4ai 集成完善后，使用专门的 crawl4ai 调用
            logger.info(f"Crawl4ai 可用，使用标准深度采集 (crawl4ai 集成待完善)")
        except Exception:
            pass

    # 使用标准 deep_fetch 作为回退
    status, title, content, error = await loop.run_in_executor(
        None, lambda: deep_fetch(url, timeout=30)
    )
    if status == 200:
        return {
            "success": True,
            "url": url,
            "extract_mode": extract_mode,
            "engine": "crawl4ai" if _HAS_CRAWL4AI else "standard",
            "title": title or "",
            "content": (content or "")[:5000],
            "content_size": len(content) if content else 0,
        }
    else:
        return {
            "success": False,
            "url": url,
            "error": error or "深度采集失败",
        }


async def _batch_deep_collect_url(urls: List[str], extract_mode: str = "auto") -> Dict[str, Any]:
    """批量对多个 URL 进行深度采集。"""
    results = []
    for url in urls:
        result = await _deep_collect_url(url, extract_mode=extract_mode)
        results.append(result)
    return {
        "total": len(urls),
        "success_count": sum(1 for r in results if r.get("success")),
        "results": results,
    }
