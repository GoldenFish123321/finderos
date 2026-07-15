"""
app/mcp/registry.py — MCP 工具注册中心 (v0.10 新增)

数据库驱动的工具注册中心，替代原来的 tools.py 硬编码注册。

功能:
- 启动时从 mcp_tools 表加载所有 enabled 工具
- 动态注册/注销工具到 MCPServer
- 支持热重载 (通过管理后台触发)
- 根据 handler_module 动态加载处理函数

设计理念:
- builtin 型工具: handler_module 指向 builtin_tools 包中的函数
- api 型工具: 封装 HTTP 请求为 MCP 工具
- 工具元数据 (name/description/input_schema) 完全由数据库驱动
"""

import importlib
import inspect
import json
import logging
import pkgutil
import types
from typing import Any, Callable, Dict, List, Optional, Union, get_args, get_origin, get_type_hints

from app.mcp.server import MCPServer, MCPTool

logger = logging.getLogger(__name__)

# 内置工具处理函数映射表（快速查找，避免每次 importlib）
_BUILTIN_HANDLERS: Dict[str, Callable] = {}
_BUILTIN_SCAN_COMPLETE = False


def _load_builtin_handlers():
    """预加载所有 builtin_tools 模块中的处理函数。"""
    global _BUILTIN_HANDLERS, _BUILTIN_SCAN_COMPLETE
    if _BUILTIN_SCAN_COMPLETE:
        return

    import app.mcp.builtin_tools as builtin_package
    modules = [
        info.name for info in pkgutil.iter_modules(
            builtin_package.__path__, builtin_package.__name__ + "."
        ) if not info.name.rsplit(".", 1)[-1].startswith("_")
    ]

    for module_name in modules:
        try:
            module = importlib.import_module(module_name)
            for attr_name in dir(module):
                if not attr_name.startswith("_") or attr_name.startswith("__"):
                    continue
                attr = getattr(module, attr_name)
                if callable(attr) and getattr(attr, "__module__", "") == module_name:
                    _BUILTIN_HANDLERS[f"{module_name}.{attr_name}"] = attr
        except Exception as e:
            logger.warning(f"加载内置工具模块失败: {module_name} — {e}")

    logger.info(f"预加载了 {len(_BUILTIN_HANDLERS)} 个内置工具处理函数")
    _BUILTIN_SCAN_COMPLETE = True


def _annotation_schema(annotation) -> Dict[str, Any]:
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin in (list, tuple, set) or "Sequence" in str(origin):
        return {"type": "array", "items": _annotation_schema(args[0] if args else str)}
    if origin is dict:
        return {"type": "object"}
    if origin in (Union, types.UnionType):
        concrete = [arg for arg in args if arg is not type(None)]
        return _annotation_schema(concrete[0]) if len(concrete) == 1 else {"type": "string"}
    if annotation is bool:
        return {"type": "boolean"}
    if annotation is int:
        return {"type": "integer"}
    if annotation is float:
        return {"type": "number"}
    if annotation is dict:
        return {"type": "object"}
    return {"type": "string"}


def discover_builtin_tool_definitions() -> List[Dict[str, Any]]:
    """Build fallback MCP definitions from every discovered builtin handler."""
    _load_builtin_handlers()
    definitions = []
    for full_path, handler in sorted(_BUILTIN_HANDLERS.items()):
        try:
            hints = get_type_hints(handler)
        except Exception:
            hints = {}
        properties = {}
        required = []
        for name, parameter in inspect.signature(handler).parameters.items():
            annotation = hints.get(name, parameter.annotation)
            properties[name] = {**_annotation_schema(annotation), "description": name}
            if parameter.default is inspect.Parameter.empty:
                required.append(name)
            else:
                properties[name]["default"] = parameter.default
        schema = {"type": "object", "properties": properties}
        if required:
            schema["required"] = required
        definitions.append({
            "name": handler.__name__.lstrip("_"),
            "description": inspect.getdoc(handler) or handler.__name__.lstrip("_"),
            "input_schema": schema,
            "handler": handler,
            "handler_module": full_path,
        })
    return definitions


def _resolve_handler(handler_module: str) -> Optional[Callable]:
    """解析 handler_module 路径为实际可调用函数。

    支持两种格式:
    1. 完整路径: app.mcp.builtin_tools.warehouse_tools._search_warehouse
    2. 短路径: warehouse_tools._search_warehouse (自动补全前缀)
    """
    if not handler_module:
        return None

    # 先尝试内置映射表
    if handler_module in _BUILTIN_HANDLERS:
        return _BUILTIN_HANDLERS[handler_module]

    # 尝试短路径自动补全
    if not handler_module.startswith("app."):
        for prefix in ["app.mcp.builtin_tools.", "app.mcp."]:
            full_path = prefix + handler_module
            if full_path in _BUILTIN_HANDLERS:
                return _BUILTIN_HANDLERS[full_path]

    # 尝试动态 import
    try:
        parts = handler_module.rsplit(".", 1)
        if len(parts) == 2:
            module_name, func_name = parts
            module = importlib.import_module(module_name)
            return getattr(module, func_name, None)
    except Exception as e:
        logger.warning(f"动态加载处理函数失败: {handler_module} — {e}")

    return None


def _build_tool_from_db_row(row: Dict[str, Any]) -> Optional[MCPTool]:
    """从数据库行构建 MCPTool 实例。"""
    tool_type = row.get("tool_type", "builtin")

    if tool_type == "builtin":
        handler = _resolve_handler(row.get("handler_module", ""))
        if not handler:
            logger.warning(f"工具 {row['name']} 的处理函数未找到: {row.get('handler_module')}")
            return None

        try:
            input_schema = json.loads(row.get("input_schema", "{}"))
        except (json.JSONDecodeError, TypeError):
            input_schema = {}

        return MCPTool(
            name=row["name"],
            description=row.get("description", ""),
            input_schema=input_schema,
            handler=handler,
        )

    elif tool_type == "api":
        # API 型工具：封装 HTTP 调用
        api_url = row.get("api_url", "")
        api_method = row.get("api_method", "GET")
        api_headers_str = row.get("api_headers", "{}")

        try:
            api_headers = json.loads(api_headers_str)
        except (json.JSONDecodeError, TypeError):
            api_headers = {}

        try:
            input_schema = json.loads(row.get("input_schema", "{}"))
        except (json.JSONDecodeError, TypeError):
            input_schema = {}

        async def api_handler(**kwargs) -> Any:
            import urllib.parse
            import asyncio
            from app.utils.safe_http import SafeHttpError, safe_http_request
            # 构建 URL（替换路径参数）
            final_url = api_url
            for key, value in kwargs.items():
                final_url = final_url.replace(f"{{{key}}}", str(value))

            # 对于 GET 请求，剩余参数作为 query string
            query_params = {k: v for k, v in kwargs.items() if f"{{{k}}}" not in api_url}
            if query_params and api_method.upper() == "GET":
                qs = urllib.parse.urlencode(query_params)
                final_url += ("&" if "?" in final_url else "?") + qs

            def _sync_call():
                try:
                    data = None
                    if api_method.upper() == "POST" and query_params:
                        data = json.dumps(query_params).encode("utf-8")
                        api_headers["Content-Type"] = "application/json"
                    response = safe_http_request(
                        final_url, method=api_method, headers=api_headers,
                        body=data, timeout=30, max_bytes=1024 * 1024,
                    )
                    if 300 <= response.status < 400:
                        return {"error": "MCP API 工具不允许重定向"}
                    body = response.body.decode("utf-8", errors="replace")
                    try:
                        return json.loads(body)
                    except json.JSONDecodeError:
                        return {"raw": body[:5000]}
                except SafeHttpError:
                    return {"error": "MCP API 目标地址或响应不符合安全策略"}
                except Exception as e:
                    logger.warning("MCP API 工具调用失败: %s", e)
                    return {"error": "MCP API 工具调用失败"}

            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _sync_call)

        return MCPTool(
            name=row["name"],
            description=row.get("description", ""),
            input_schema=input_schema,
            handler=api_handler,
        )

    return None


class MCPToolRegistry:
    """MCP 工具注册中心 — 数据库驱动。

    单例模式，管理所有 MCP 工具的注册/注销/重载。
    """

    _instance: Optional["MCPToolRegistry"] = None

    def __init__(self, server: Optional[MCPServer] = None):
        self._server = server or MCPServer.get_instance()
        self._loaded_tool_names: set = set()

    @classmethod
    def get_instance(cls, server: Optional[MCPServer] = None) -> "MCPToolRegistry":
        if cls._instance is None:
            cls._instance = cls(server)
        return cls._instance

    # ── 加载与重载 ────────────────────────────────────────

    def load_all_from_db(self) -> int:
        """从数据库加载所有启用的工具并注册到 MCPServer。

        Returns:
            成功加载的工具数量。
        """
        from app.models.mcp_tool import MCPToolRepository

        # 预加载内置处理函数
        _load_builtin_handlers()

        tools = MCPToolRepository.get_enabled()
        count = 0

        for row in tools:
            tool = _build_tool_from_db_row(row)
            if tool:
                self._server.register_tool(tool)
                self._loaded_tool_names.add(tool.name)
                count += 1
            else:
                logger.warning(f"跳过工具: {row['name']} (无法构建)")

        logger.info(f"从数据库加载了 {count} 个 MCP 工具")
        return count

    def reload_all(self) -> int:
        """热重载所有工具（从数据库重新加载）。

        先清除所有已注册的工具，再重新从数据库加载。
        """
        # 清除所有已注册工具
        for name in list(self._loaded_tool_names):
            self._server.unregister_tool(name)
        self._loaded_tool_names.clear()

        return self.load_all_from_db()

    def register_tool_from_db(self, tool_name: str) -> bool:
        """从数据库加载单个工具并注册。"""
        from app.models.mcp_tool import MCPToolRepository

        _load_builtin_handlers()
        row = MCPToolRepository.get_by_name(tool_name)
        if not row:
            logger.warning(f"工具不存在于数据库: {tool_name}")
            return False

        if not row.get("is_enabled"):
            logger.warning(f"工具已禁用: {tool_name}")
            return False

        tool = _build_tool_from_db_row(row)
        if tool:
            self._server.register_tool(tool)
            self._loaded_tool_names.add(tool.name)
            return True
        return False

    def unregister_tool(self, tool_name: str) -> bool:
        """从 MCPServer 注销指定工具。"""
        if tool_name in self._loaded_tool_names:
            self._server.unregister_tool(tool_name)
            self._loaded_tool_names.discard(tool_name)
            return True
        return False

    # ── 状态查询 ──────────────────────────────────────────

    @property
    def loaded_count(self) -> int:
        return len(self._loaded_tool_names)

    @property
    def loaded_tool_names(self) -> List[str]:
        return list(self._loaded_tool_names)

    def is_loaded(self, tool_name: str) -> bool:
        return tool_name in self._loaded_tool_names
