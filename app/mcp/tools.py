"""
app/mcp/tools.py — MCP 工具注册入口

提供 register_all_tools() 和 get_tool_names() 两个核心函数。
工具定义与 handler 实现通过 MCPToolRegistry（数据库驱动）进行管理，
不再在此文件中硬编码工具列表。
"""

import logging
from typing import List, Optional

from app.mcp.server import MCPServer

logger = logging.getLogger(__name__)


def register_all_tools(server: Optional[MCPServer] = None) -> MCPServer:
    """向 MCP Server 注册所有工具（从数据库加载）。

    使用 MCPToolRegistry 从数据库加载工具记录。

    Args:
        server: MCP Server 实例，为 None 时使用全局单例。

    Returns:
        MCPServer 实例。
    """
    if server is None:
        server = MCPServer.get_instance()

    from app.mcp.registry import MCPToolRegistry
    registry = MCPToolRegistry.get_instance(server)
    count = registry.load_all_from_db()
    logger.info(f"已从数据库注册 {count} 个 MCP 工具")
    return server


def get_tool_names() -> List[str]:
    """获取所有已启用的工具名称列表。"""
    from app.models.mcp_tool import MCPToolRepository
    tools = MCPToolRepository.get_enabled()
    return [t["name"] for t in tools]
