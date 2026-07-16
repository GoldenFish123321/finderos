"""
app/mcp/builtin_tools/__init__.py

按分类组织的 MCP 工具处理函数包。
每个模块对应一个工具分类，包含该分类下的所有 handler 函数。
"""

from app.mcp.builtin_tools.warehouse_tools import (
    _search_warehouse,
    _get_recent_warehouse_data,
    _get_warehouse_stats,
    _search_warehouse_fulltext,
)
from app.mcp.builtin_tools.collect_tools import (
    _collect_web_data,
    _deep_collect_url,
    _list_watch_sources,
)
from app.mcp.builtin_tools.employee_tools import (
    _list_digital_employees,
    _invoke_digital_employee,
)
from app.mcp.builtin_tools.model_tools import (
    _list_ai_models,
    _get_default_model,
)
from app.mcp.builtin_tools.chat_tools import (
    _list_conversations,
    _get_conversation_messages,
)
from app.mcp.builtin_tools.entertainment_tools import (
    _get_random_music,
)
from app.mcp.builtin_tools.crawl4ai_tools import (
    _collect_with_crawl4ai,
    _batch_deep_collect,
)
from app.mcp.builtin_tools.system_tools import (
    _load_skill,
    _get_system_stats,
)
