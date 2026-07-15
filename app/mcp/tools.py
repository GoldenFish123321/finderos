"""
app/mcp/tools.py — MCP 工具定义与注册

定义瞭望与问数系统所有对外暴露的 AI 工具（遵循 MCP 协议）。
每个工具包含：
- name: 唯一标识符
- description: 自然语言描述（供 LLM 理解用途）
- inputSchema: JSON Schema 参数定义
- handler: 实际执行函数

工具分类（共 18 个工具，v0.10 补齐）：
1. 数据仓库类: search_warehouse, get_recent_warehouse_data, get_warehouse_stats, search_warehouse_fulltext
2. 数据采集类: collect_web_data, deep_collect_url, list_watch_sources
3. 数字员工类: list_digital_employees, invoke_digital_employee
4. AI 模型类: list_ai_models, get_default_model
5. Crawl4ai 增强类: collect_with_crawl4ai, batch_deep_collect
6. 音乐/娱乐类: get_random_music
7. 对话管理类: list_conversations, get_conversation_messages
8. 技能管理类: load_skill
9. 系统管理类: get_system_stats
"""

import json
import logging
from typing import Any, Dict, List, Optional

from app.mcp.server import MCPServer, MCPTool

# v0.10: 从 builtin_tools 导入新增的 handler（避免在 tools.py 中重复定义）
from app.mcp.builtin_tools.warehouse_tools import _search_warehouse_fulltext
from app.mcp.builtin_tools.collect_tools import _list_watch_sources
from app.mcp.builtin_tools.employee_tools import _invoke_digital_employee
from app.mcp.builtin_tools.model_tools import _list_ai_models, _get_default_model
from app.mcp.builtin_tools.crawl4ai_tools import _collect_with_crawl4ai, _batch_deep_collect
from app.mcp.builtin_tools.system_tools import _get_system_stats

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
    import asyncio
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


async def _get_random_music() -> Dict[str, Any]:
    """随机获取一首歌曲（从网易云音乐热歌榜）。"""
    import asyncio
    import random as _random
    import urllib.request
    import json as _json

    def _sync_fetch():
        from app.utils.safe_http import safe_http_request
        url = "https://api.injahow.cn/meting/?server=netease&type=playlist&id=3778678"
        headers = {"User-Agent": "FinderOS/1.0", "Accept": "application/json"}
        try:
            response = safe_http_request(
                url, headers=headers, timeout=15, max_bytes=1024 * 1024
            )
            body = response.body.decode("utf-8", errors="replace")
            songs = _json.loads(body)
            if isinstance(songs, list) and len(songs) > 0:
                song = _random.choice(songs)
                return {
                    "success": True,
                    "name": song.get("name", ""),
                    "artist": song.get("artist", ""),
                    "cover": song.get("pic", ""),
                    "url": song.get("url", ""),
                    "source": "网易云音乐热歌榜",
                }
            return {"success": False, "error": "歌曲列表为空"}
        except Exception as e:
            logger.warning(f"get_random_music 调用失败: {e}")
            # 回退：返回本地 Mock 歌曲
            mock_songs = [
                {"name": "晴天", "artist": "周杰伦",
                 "cover": "https://picsum.photos/seed/music1/160/160",
                 "url": "https://music.163.com/"},
                {"name": "夜曲", "artist": "周杰伦",
                 "cover": "https://picsum.photos/seed/music2/160/160",
                 "url": "https://music.163.com/"},
                {"name": "稻香", "artist": "周杰伦",
                 "cover": "https://picsum.photos/seed/music3/160/160",
                 "url": "https://music.163.com/"},
            ]
            song = _random.choice(mock_songs)
            return {
                "success": True,
                "name": song["name"],
                "artist": song["artist"],
                "cover": song["cover"],
                "url": song["url"],
                "source": "本地曲库（Mock）",
                "note": f"API 调用失败: {str(e)[:100]}",
            }

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_fetch)


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


def _get_conversation_messages(conversation_id: int, limit: int = 20,
                               username: str = "") -> Dict[str, Any]:
    """获取指定对话的消息历史（含所有权验证）。"""
    from app.models.conversation import ConversationRepository
    # 所有权验证：确保用户只能读取自己的对话
    if username:
        conv = ConversationRepository.get_by_id(conversation_id)
        if not conv or conv.get("username", "") != username:
            return {
                "conversation_id": conversation_id,
                "total": 0,
                "messages": [],
                "error": "对话不存在或无权访问",
            }
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


def _load_skill(skill_name: str) -> Dict[str, Any]:
    """加载指定技能的 prompt 模板指令。

    技能统一为 Prompt 模板，LLM 获取后按模板中的指示执行任务。
    """
    from app.models.skill import SkillRepository
    skill = SkillRepository.get_by_name(skill_name.strip())
    if not skill:
        return {
            "success": False,
            "error": f"技能「{skill_name}」不存在",
            "hint": "请检查技能名称拼写，或使用 /tools 查看可用工具列表",
        }
    if skill.get("is_enabled") != 1:
        return {
            "success": False,
            "error": f"技能「{skill_name}」已被禁用",
        }

    return {
        "success": True,
        "skill_name": skill["name"],
        "description": skill.get("description", ""),
        "content": skill.get("prompt_template", ""),
        "usage": "请将以上 content 作为你的系统指令严格遵循，完成用户的任务。如需使用 MCP 工具，请在 content 中自行描述。",
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
    {
        "name": "search_warehouse_fulltext",
        "description": (
            "使用 FTS5 全文检索在数据仓库中搜索内容（v0.10 新增）。"
            "相比 search_warehouse 的关键词搜索，全文检索更准确，支持多词组合和短语搜索。"
            "当需要精确搜索或 search_warehouse 返回结果不理想时使用此工具。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "全文检索查询词（支持多词组合）",
                },
                "limit": {
                    "type": "integer",
                    "description": "返回结果数量上限，默认10",
                    "default": 10,
                },
            },
            "required": ["query"],
        },
        "handler": _search_warehouse_fulltext,
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
    {
        "name": "list_watch_sources",
        "description": (
            "列出系统中所有启用的瞭望采集源（v0.10 新增）。"
            "返回每个瞭望源的名称、描述和 URL 模板，方便了解当前可用的数据采集渠道。"
            "当用户询问「有哪些采集源」「可以从哪些网站采集数据」时使用。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
        "handler": _list_watch_sources,
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
    {
        "name": "invoke_digital_employee",
        "description": (
            "调用指定数字员工执行任务（v0.10 新增）。"
            "支持按名称或 ID 查找员工，支持 LLM 型（通过对话系统调用）和 API 型（直接 HTTP 调用）。"
            "当用户明确要求「让XX员工帮我做XX」「调用XX员工」「@XX」时使用。"
            "不确定有哪些员工时请先使用 list_digital_employees。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "employee_name": {
                    "type": "string",
                    "description": "要调用的数字员工名称或 ID",
                },
                "message": {
                    "type": "string",
                    "description": "发送给该员工的指令或消息",
                },
            },
            "required": ["employee_name", "message"],
        },
        "handler": _invoke_digital_employee,
    },

    # ── AI 模型类 (v0.10 新增) ──
    {
        "name": "list_ai_models",
        "description": (
            "列出系统中所有可用的 AI 大语言模型（v0.10 新增）。"
            "返回每个模型的名称、提供商、模型标识和分类信息。"
            "当用户询问「有哪些AI模型」「可以用哪些模型」「XX模型还能用吗」时使用。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
        "handler": _list_ai_models,
    },
    {
        "name": "get_default_model",
        "description": (
            "获取当前系统设置的默认 AI 模型信息（v0.10 新增）。"
            "当用户询问「默认模型是什么」「当前用的是什么模型」时使用。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
        "handler": _get_default_model,
    },

    # ── 音乐/娱乐类 ──
    {
        "name": "get_random_music",
        "description": (
            "随机推荐一首歌曲。从网易云音乐热歌榜中随机选取一首，返回歌曲名、歌手、封面图和试听链接。"
            "当用户说「来首歌」「随机音乐」「推荐一首歌」「放首歌」「来点音乐」时使用此工具。"
            "注意：此工具直接返回歌曲数据，调用后应基于数据向用户展示歌曲信息。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
        "handler": _get_random_music,
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
                "username": {
                    "type": "string",
                    "description": "当前用户名（由系统自动填充，用于所有权验证）",
                },
            },
            "required": ["conversation_id"],
        },
        "handler": _get_conversation_messages,
    },

    # ── Crawl4ai 增强类 (v0.10 新增) ──
    {
        "name": "collect_with_crawl4ai",
        "description": (
            "使用 Crawl4ai 对指定 URL 进行智能深度采集（v0.10 新增）。"
            "相比普通 deep_collect_url，Crawl4ai 能更好地处理 JavaScript 渲染页面和复杂网页结构。"
            "Crawl4ai 不可用时自动回退到标准深度采集。"
            "当用户要求「用Crawl4ai采集」「智能抓取XX网站」时使用。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "要采集的目标网页 URL（必须是完整 HTTP/HTTPS 链接）",
                },
                "extract_mode": {
                    "type": "string",
                    "description": "提取模式：auto（自动）、text（纯文本）、html（HTML），默认 auto",
                    "default": "auto",
                },
            },
            "required": ["url"],
        },
        "handler": _collect_with_crawl4ai,
    },
    {
        "name": "batch_deep_collect",
        "description": (
            "批量对多个 URL 进行深度采集（v0.10 新增）。"
            "一次性处理多个链接，返回每个链接的采集结果。"
            "当用户提供多个 URL 要求「批量采集」「把这些链接都抓取」时使用。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "urls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要批量采集的 URL 列表（每个必须是完整 HTTP/HTTPS 链接）",
                },
                "extract_mode": {
                    "type": "string",
                    "description": "提取模式：auto（自动）、text（纯文本）、html（HTML），默认 auto",
                    "default": "auto",
                },
            },
            "required": ["urls"],
        },
        "handler": _batch_deep_collect,
    },

    # ── 技能管理类 (v0.7 新增) ──
    {
        "name": "load_skill",
        "description": (
            "加载指定技能的完整执行指令。"
            "当系统提示中的「可用技能」列表里存在你需要的技能时，调用此工具获取该技能的详细 prompt 模板或 function 映射。"
            "不要猜测技能内容，始终通过此工具按需加载。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "要加载的技能名称（必须与可用技能列表中的名称完全一致）",
                },
            },
            "required": ["skill_name"],
        },
        "handler": _load_skill,
    },

    # ── 系统管理类 (v0.10 新增) ──
    {
        "name": "get_system_stats",
        "description": (
            "获取系统统计概览（v0.10 新增），包括用户数、数据仓库记录数、数字员工数、"
            "AI 模型数和对话数等关键指标。"
            "当用户询问「系统状态」「有多少用户」「系统概况」时使用。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
        "handler": _get_system_stats,
    },
]


def register_all_tools(server: Optional[MCPServer] = None) -> MCPServer:
    """向 MCP Server 注册所有工具 (v0.10: 优先从数据库加载)。

    优先使用 MCPToolRegistry 从数据库加载；
    如果数据库没有工具记录，回退到代码定义的 ALL_TOOL_DEFINITIONS。

    Args:
        server: MCP Server 实例，为 None 时使用全局单例。

    Returns:
        MCPServer 实例。
    """
    if server is None:
        server = MCPServer.get_instance()

    # 优先从数据库加载
    try:
        from app.mcp.registry import MCPToolRegistry
        registry = MCPToolRegistry.get_instance(server)
        count = registry.load_all_from_db()
        if count > 0:
            logger.info(f"已从数据库注册 {count} 个 MCP 工具")
            return server
    except Exception as e:
        logger.warning(f"从数据库加载工具失败，回退到代码定义: {e}")

    # 回退：自动发现 builtin_tools，避免此文件的旧重复定义发生漂移。
    from app.mcp.registry import discover_builtin_tool_definitions
    fallback_definitions = discover_builtin_tool_definitions()
    tools = []
    for tool_def in fallback_definitions:
        tool = MCPTool(
            name=tool_def["name"],
            description=tool_def["description"],
            input_schema=tool_def["input_schema"],
            handler=tool_def["handler"],
        )
        tools.append(tool)

    server.register_tools(tools)
    logger.info(f"已从自动发现注册 {len(tools)} 个 MCP 工具: {[t.name for t in tools]}")
    return server


def get_tool_names() -> List[str]:
    """获取所有已定义的工具名称列表。"""
    from app.mcp.registry import discover_builtin_tool_definitions
    return [tool["name"] for tool in discover_builtin_tool_definitions()]
