"""
app/mcp/__init__.py — MCP (Model Context Protocol) 模块

本模块实现了 MCP 协议的核心子集，用于标准化 AI 工具调用：
- 工具注册与发现 (tools/list, tools/call)
- OpenAI Function Calling 格式转换
- 进程内直连传输（零序列化开销）

协议版本: MCP 2024-11-05 兼容子集
"""
from app.mcp.server import MCPServer
from app.mcp.client import MCPClient
from app.mcp.tools import register_all_tools

# v0.6.0: 注册中心
from app.mcp.registry import MCPToolRegistry

__all__ = ["MCPServer", "MCPClient", "register_all_tools", "MCPToolRegistry"]
