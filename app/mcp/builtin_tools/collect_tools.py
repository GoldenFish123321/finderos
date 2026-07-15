"""
collect_tools.py — 数据采集类 MCP 工具处理函数

工具:
- collect_web_data: 全网瞭望采集
- deep_collect_url: 深度采集 URL
- list_watch_sources: 瞭望源列表 (v0.4.2 新增)
"""

import asyncio
import json as _json
import urllib.parse
from typing import Any, Dict, List, Optional


async def _collect_web_data(keyword: str, source_ids: Optional[List[int]] = None) -> Dict[str, Any]:
    """执行全网瞭望数据采集（异步执行，在线程池中运行）。"""
    from app.models.watch_source import WatchSourceRepository
    from app.models.watch_result import WatchResultRepository
    from app.services.collector import fetch_and_parse

    if source_ids:
        sources = []
        for sid in source_ids:
            s = WatchSourceRepository.get_by_id(sid)
            if s and s.get("is_enabled") == 1:
                sources.append(s)
    else:
        sources = WatchSourceRepository.get_enabled()

    if not sources:
        return {"keyword": keyword, "total_collected": 0, "items": [], "msg": "没有可用的瞭望源"}

    def _do_collect():
        all_news = []
        for source in sources:
            url_template = source["url_template"]
            encoded_kw = urllib.parse.quote(keyword, encoding="utf-8")
            request_url = url_template.replace("{keyword}", encoded_kw).replace("{page}", "0")

            raw_headers = WatchSourceRepository.get_headers(source["id"])
            from app.utils.security import has_crlf
            headers = {}
            for k, v in raw_headers.items():
                if k.lower() in ("accept-encoding", "host", "sec-fetch-dest", "sec-fetch-mode",
                                 "sec-fetch-site", "sec-fetch-user", "connection", "cache-control"):
                    continue
                if has_crlf(k) or has_crlf(v):
                    continue
                headers[k] = v

            parser = "sogou_news" if "sogou" in request_url.lower() else "baidu_news"
            status, size, text, parsed_news = fetch_and_parse(
                request_url, headers=headers, parser=parser, timeout=15
            )

            for news in parsed_news:
                news_link = news.get("link", "")
                WatchResultRepository.create_if_not_exists(
                    source_id=source["id"],
                    keyword=keyword,
                    request_url=news_link or request_url,
                    response_status=status,
                    response_size=len(_json.dumps(news, ensure_ascii=False).encode("utf-8")),
                    result_data=_json.dumps(news, ensure_ascii=False),
                )
                all_news.append({
                    "title": news.get("title", ""),
                    "link": news_link,
                    "summary": (news.get("summary", "") or "")[:200],
                    "source_name": news.get("source_name", source["name"]),
                })
        return all_news

    loop = asyncio.get_event_loop()
    all_news = await loop.run_in_executor(None, _do_collect)

    return {
        "keyword": keyword,
        "total_collected": len(all_news),
        "items": all_news[:20],
    }


async def _deep_collect_url(url: str) -> Dict[str, Any]:
    """对指定 URL 执行深度内容采集。"""
    from app.services.deep_collector import deep_fetch

    loop = asyncio.get_event_loop()
    status, title, content, error = await loop.run_in_executor(
        None, lambda: deep_fetch(url, timeout=30)
    )
    if status == 200:
        return {
            "success": True,
            "title": title or "",
            "content": (content or "")[:3000],
            "content_size": len(content) if content else 0,
        }
    else:
        return {
            "success": False,
            "error": error or "深度采集失败",
        }


def _list_watch_sources() -> Dict[str, Any]:
    """列出所有启用的瞭望采集源（v0.4.2 新增）。"""
    from app.models.watch_source import WatchSourceRepository
    sources = WatchSourceRepository.get_enabled()
    return {
        "total": len(sources),
        "sources": [
            {
                "id": s["id"],
                "name": s["name"],
                "description": s.get("description", ""),
                "url_template": s.get("url_template", ""),
            }
            for s in sources
        ],
    }
