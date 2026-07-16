"""
app/mcp/tools.py — MCP 工具注册入口

提供 register_all_tools() 和 get_tool_names() 两个核心函数。
工具定义与 handler 实现已迁移至 builtin_tools/ 包，通过 MCPToolRegistry
（数据库驱动）和 discover_builtin_tool_definitions()（自动发现）进行管理，
不再在此文件中硬编码工具列表。
"""

import logging
from typing import List, Optional

from app.mcp.server import MCPServer, MCPTool

logger = logging.getLogger(__name__)


def register_all_tools(server: Optional[MCPServer] = None) -> MCPServer:
    """向 MCP Server 注册所有工具（优先从数据库加载）。

    优先使用 MCPToolRegistry 从数据库加载工具记录；
    如果数据库没有工具记录，回退到 discover_builtin_tool_definitions()
    自动发现 builtin_tools/ 包中的所有 handler。

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
        logger.warning(f"从数据库加载工具失败，回退到自动发现: {e}")

    # 回退：自动发现 builtin_tools/ 包中的所有 handler
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
