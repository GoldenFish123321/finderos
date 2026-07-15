"""
app/mcp/server.py — MCP Server 核心实现

进程内 MCP 服务器，管理工具注册表并提供：
- tools/list: 列出所有注册的工具及其 JSON Schema
- tools/call: 调用指定工具并返回结果
- OpenAI Function Calling 格式导出

设计理念：遵循 MCP 协议规范，但使用进程内直调（零网络开销）。
"""

import json
import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class MCPTool:
    """MCP 工具定义，遵循 MCP 协议 Tool 对象规范。"""

    def __init__(
        self,
        name: str,
        description: str,
        input_schema: Dict[str, Any],
        handler: Callable[..., Any],
    ):
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.handler = handler

    def to_mcp_dict(self) -> Dict[str, Any]:
        """转为 MCP 协议的 Tool 对象格式。"""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }

    def to_openai_function(self) -> Dict[str, Any]:
        """转为 OpenAI Function Calling 的 function 定义。

        OpenAI 格式:
        {
            "type": "function",
            "function": {
                "name": "...",
                "description": "...",
                "parameters": {...}
            }
        }
        """
        params = dict(self.input_schema)  # 浅拷贝
        # OpenAI 要求 parameters 包含 type: object
        if "type" not in params:
            params = {"type": "object", "properties": params, "required": []}
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": params,
            },
        }

    async def call(self, arguments: Dict[str, Any]) -> Any:
        """调用工具处理函数。支持同步和异步 handler。"""
        import asyncio
        try:
            result = self.handler(**arguments)
            if asyncio.iscoroutine(result):
                result = await result
            return result
        except TypeError as e:
            raise ValueError(f"工具 {self.name} 参数错误: {e}") from e
        except Exception as e:
            logger.error(f"工具 {self.name} 执行失败: {e}", exc_info=True)
            raise


class MCPServer:
    """进程内 MCP 服务器。

    管理工具注册表，提供 MCP 协议兼容的 API。
    单例模式：整个应用共享一个实例。
    """

    _instance: Optional["MCPServer"] = None

    def __init__(self):
        self._tools: Dict[str, MCPTool] = {}
        self._resources: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def get_instance(cls) -> "MCPServer":
        """获取全局单例。"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── 工具管理 ─────────────────────────────────────────

    def register_tool(self, tool: MCPTool) -> None:
        """注册一个工具。同名工具会覆盖旧定义。"""
        self._tools[tool.name] = tool
        logger.info(f"MCP 工具已注册: {tool.name}")

    def register_tools(self, tools: List[MCPTool]) -> None:
        """批量注册工具。"""
        for tool in tools:
            self.register_tool(tool)

    def get_tool(self, name: str) -> Optional[MCPTool]:
        """按名称获取工具。"""
        return self._tools.get(name)

    # ── MCP 协议方法 ─────────────────────────────────────

    def list_tools(self) -> List[Dict[str, Any]]:
        """tools/list — 返回所有已注册工具的定义列表（MCP 格式）。"""
        return [tool.to_mcp_dict() for tool in self._tools.values()]

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """tools/call — 调用指定工具并返回 MCP 格式结果。

        返回格式（MCP CallToolResult）:
        {
            "content": [
                {"type": "text", "text": "..."}
            ],
            "isError": false
        }
        """
        tool = self._tools.get(name)
        if not tool:
            return {
                "content": [{"type": "text", "text": f"工具不存在: {name}"}],
                "isError": True,
            }
        try:
            result = await tool.call(arguments)
            # 将结果序列化为文本
            if isinstance(result, str):
                text = result
            elif isinstance(result, (dict, list)):
                text = json.dumps(result, ensure_ascii=False, indent=2)
            else:
                text = str(result)
            return {
                "content": [{"type": "text", "text": text}],
                "isError": False,
            }
        except Exception as e:
            return {
                "content": [{"type": "text", "text": str(e)}],
                "isError": True,
            }

    # ── OpenAI Function Calling 格式导出 ──────────────────

    def get_openai_tools(self, tool_names: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """导出为 OpenAI Function Calling tools 数组格式。

        Args:
            tool_names: 要导出的工具名称列表。None 表示全部导出。
        """
        tools = []
        for name, tool in self._tools.items():
            if tool_names is None or name in tool_names:
                tools.append(tool.to_openai_function())
        return tools

    def get_tool_descriptions_for_prompt(self) -> str:
        """生成工具描述文本（用于注入 system prompt，无 API Key 时的回退方案）。"""
        lines = ["可用工具列表："]
        for i, (name, tool) in enumerate(self._tools.items(), 1):
            # 提取参数说明
            props = tool.input_schema.get("properties", {})
            required = tool.input_schema.get("required", [])
            param_strs = []
            for pname, pinfo in props.items():
                req_mark = "（必填）" if pname in required else "（可选）"
                param_strs.append(f"  - {pname}: {pinfo.get('description', '')} {req_mark}")
            params_text = "\n".join(param_strs) if param_strs else "  无参数"
            lines.append(f"{i}. **{name}**: {tool.description}\n{params_text}")
        return "\n".join(lines)

    # ── 统计信息 ─────────────────────────────────────────

    @property
    def tool_count(self) -> int:
        return len(self._tools)

    @property
    def tool_names(self) -> List[str]:
        return list(self._tools.keys())
