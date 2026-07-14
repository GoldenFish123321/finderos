"""
app/mcp/tools.py — MCP 工具定义与注册

定义瞭望与问数系统所有对外暴露的 AI 工具（遵循 MCP 协议）。
每个工具包含：
- name: 唯一标识符
- description: 自然语言描述（供 LLM 理解用途）
- inputSchema: JSON Schema 参数定义
- handler: 实际执行函数

工具分类：
1. 数据仓库类: search_warehouse, get_recent_warehouse_data, get_warehouse_stats
2. 数据采集类: collect_web_data, deep_collect_url
3. 数字员工类: list_digital_employees, invoke_digital_employee
4. 对话管理类: list_conversations, get_conversation_messages
"""

import json
import logging
from typing import Any, Dict, List, Optional

from app.mcp.server import MCPServer, MCPTool

logger = logging.getLogger(__name__)


# ============================================================
# 工具处理函数
# ============================================================

def _search_warehouse(keyword: str, limit: int = 10) -> Dict[str, Any]:
    """在数据仓库中搜索关键词相关内容。"""
    from app.models.data_warehouse import DataWarehouseRepository
    items = DataWarehouseRepository.search(keyword, limit=limit)
    return {
        "total": len(items),
        "items": [
            {
                "id": it.get("id"),
                "title": it.get("title", ""),
                "summary": (it.get("summary", "") or "")[:300],
                "source_name": it.get("source_name", ""),
                "link": it.get("link", ""),
                "created_at": it.get("created_at", ""),
            }
            for it in items
        ],
    }


def _get_recent_warehouse_data(limit: int = 10) -> Dict[str, Any]:
    """获取数据仓库中最新入库的数据。"""
    from app.models.data_warehouse import DataWarehouseRepository
    items = DataWarehouseRepository.get_recent(limit=limit)
    return {
        "total": len(items),
        "items": [
            {
                "id": it.get("id"),
                "title": it.get("title", ""),
                "summary": (it.get("summary", "") or "")[:300],
                "source_name": it.get("source_name", ""),
                "link": it.get("link", ""),
                "is_deep_collected": bool(it.get("is_deep_collected", 0)),
                "created_at": it.get("created_at", ""),
            }
            for it in items
        ],
    }


def _get_warehouse_stats() -> Dict[str, Any]:
    """获取数据仓库的统计信息。"""
    from app.models.data_warehouse import DataWarehouseRepository
    stats = DataWarehouseRepository.get_stats()
    return stats if stats else {"total": 0, "deep_collected": 0, "top_sources": []}


async def _collect_web_data(keyword: str, source_ids: Optional[List[int]] = None) -> Dict[str, Any]:
    """执行瞭望数据采集（异步执行，在线程池中运行）。"""
    import asyncio
    import json as _json
    import urllib.parse

    from app.models.watch_source import WatchSourceRepository
    from app.models.watch_result import WatchResultRepository
    from app.services.collector import fetch_and_parse

    # 获取瞭望源
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
            encoded_kw = urllib.parse.quote(keyword)
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
    import asyncio
    from app.services.deep_collector import deep_fetch

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, lambda: deep_fetch(url, timeout=30))
    if result.get("success"):
        return {
            "success": True,
            "title": result.get("title", ""),
            "content": (result.get("content", "") or "")[:3000],
            "content_size": result.get("content_size", 0),
        }
    else:
        return {
            "success": False,
            "error": result.get("error", "深度采集失败"),
        }


def _list_digital_employees() -> Dict[str, Any]:
    """列出所有启用的数字员工。"""
    from app.models.digital_employee import DigitalEmployeeRepository
    employees = DigitalEmployeeRepository.get_enabled()
    return {
        "total": len(employees),
        "employees": [
            {
                "id": e["id"],
                "name": e["name"],
                "type": e.get("employee_type", "llm"),
                "description": e.get("description", ""),
            }
            for e in employees
        ],
    }


def _list_conversations(username: str = "", limit: int = 20) -> Dict[str, Any]:
    """列出用户的对话历史。"""
    from app.models.conversation import ConversationRepository
    conversations = ConversationRepository.get_all(username=username, limit=limit)
    return {
        "total": len(conversations),
        "conversations": [
            {
                "id": c.get("id"),
                "title": c.get("title", "新对话"),
                "msg_count": c.get("msg_count", 0),
                "updated_at": c.get("updated_at", ""),
            }
            for c in conversations
        ],
    }


def _get_conversation_messages(conversation_id: int, limit: int = 20) -> Dict[str, Any]:
    """获取指定对话的消息历史。"""
    from app.models.conversation import ConversationRepository
    messages = ConversationRepository.get_messages(conversation_id, limit=limit)
    return {
        "conversation_id": conversation_id,
        "total": len(messages),
        "messages": [
            {
                "role": m.get("role", ""),
                "content": (m.get("content", "") or "")[:2000],
                "token_count": m.get("token_count", 0),
                "created_at": m.get("created_at", ""),
            }
            for m in messages
        ],
    }


# ============================================================
# 工具定义注册表
# ============================================================

# 所有工具定义（按类别组织）
ALL_TOOL_DEFINITIONS: List[Dict[str, Any]] = [
    # ── 数据仓库类 ──
    {
        "name": "search_warehouse",
        "description": (
            "在瞭望与问数系统的数据仓库中搜索关键词相关的内容。"
            "当用户询问「有没有关于XX的数据」「搜索XX」「查找XX」「帮我找XX」等问题时使用此工具。"
            "不要用于获取最新数据或统计信息（请使用其他专用工具）。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "搜索关键词，从用户问题中提取的核心搜索词",
                },
                "limit": {
                    "type": "integer",
                    "description": "返回结果数量上限，默认10",
                    "default": 10,
                },
            },
            "required": ["keyword"],
        },
        "handler": _search_warehouse,
    },
    {
        "name": "get_recent_warehouse_data",
        "description": (
            "获取数据仓库中最新入库的数据记录。"
            "当用户询问「最新数据」「最近有什么」「看看数据仓库」「浏览数据」时使用此工具。"
            "也适用于用户没有明确关键词但想了解数据仓库内容时。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "返回记录数，默认10",
                    "default": 10,
                },
            },
        },
        "handler": _get_recent_warehouse_data,
    },
    {
        "name": "get_warehouse_stats",
        "description": (
            "获取数据仓库的统计概况，包括总记录数、已深度采集数、来源分布等。"
            "当用户询问「有多少数据」「数据统计」「数据概况」「数据分布」时使用此工具。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
        "handler": _get_warehouse_stats,
    },

    # ── 数据采集类 ──
    {
        "name": "deep_collect_url",
        "description": (
            "对指定网页 URL 进行深度内容采集，提取文章正文、标题等结构化内容。"
            "当用户提供具体URL并要求「深度采集」「抓取这个网页」「提取文章内容」「帮我看看这个链接」时使用。"
            "仅用于采集单个 URL 的详细内容，不是搜索引擎。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "要深度采集的目标网页 URL（必须是完整 HTTP/HTTPS 链接）",
                },
            },
            "required": ["url"],
        },
        "handler": _deep_collect_url,
    },
    {
        "name": "collect_web_data",
        "description": (
            "执行全网瞭望数据采集任务，从配置的瞭望源（如百度新闻、搜狗新闻等）搜索指定关键词。"
            "当用户要求「采集关于XX的新闻」「帮我在网上搜索XX」「瞭望一下XX」时使用此工具。"
            "注意：这是一个批量采集工具，不是搜索数据仓库已有内容。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "采集关键词",
                },
                "source_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "瞭望源 ID 列表，留空则使用所有启用的瞭望源",
                },
            },
            "required": ["keyword"],
        },
        "handler": _collect_web_data,
    },

    # ── 数字员工类 ──
    {
        "name": "list_digital_employees",
        "description": (
            "列出系统中所有可用的数字员工。"
            "当用户询问「有哪些数字员工」「可以用哪些助手」「@谁」或不确定该调用哪个员工时使用。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
        "handler": _list_digital_employees,
    },

    # ── 对话管理类 ──
    {
        "name": "list_conversations",
        "description": (
            "列出用户的历史对话记录。"
            "当用户询问「之前的对话」「对话历史」「我之前的提问」时使用此工具。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "username": {
                    "type": "string",
                    "description": "用户名（由系统自动填充）",
                },
                "limit": {
                    "type": "integer",
                    "description": "返回数量上限，默认20",
                    "default": 20,
                },
            },
        },
        "handler": _list_conversations,
    },
    {
        "name": "get_conversation_messages",
        "description": (
            "获取指定对话的完整消息历史。"
            "当用户指定对话ID要求「查看那个对话」「回顾之前的聊天」时使用。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "integer",
                    "description": "对话ID",
                },
                "limit": {
                    "type": "integer",
                    "description": "返回消息数量上限",
                    "default": 20,
                },
            },
            "required": ["conversation_id"],
        },
        "handler": _get_conversation_messages,
    },
]


def register_all_tools(server: Optional[MCPServer] = None) -> MCPServer:
    """向 MCP Server 注册所有工具。

    Args:
        server: MCP Server 实例，为 None 时使用全局单例。

    Returns:
        MCPServer 实例。
    """
    if server is None:
        server = MCPServer.get_instance()

    tools = []
    for tool_def in ALL_TOOL_DEFINITIONS:
        tool = MCPTool(
            name=tool_def["name"],
            description=tool_def["description"],
            input_schema=tool_def["input_schema"],
            handler=tool_def["handler"],
        )
        tools.append(tool)

    server.register_tools(tools)
    logger.info(f"已注册 {len(tools)} 个 MCP 工具: {[t.name for t in tools]}")
    return server


def get_tool_names() -> List[str]:
    """获取所有已定义的工具名称列表。"""
    return [t["name"] for t in ALL_TOOL_DEFINITIONS]
