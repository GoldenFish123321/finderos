"""
app/mcp/registry.py — MCP 工具注册中心 (v0.10 新增)

数据库驱动的工具注册中心，替代原来的 tools.py 硬编码注册。

功能:
- 启动时从 mcp_tools 表加载所有 enabled 工具
- 动态注册/注销工具到 MCPServer
- 支持热重载 (通过管理后台触发)

设计理念:
- script 型工具: 本地接口数据源 + 纯数据转换脚本
- 工具元数据 (name/description/input_schema) 完全由数据库驱动
"""

import json
import logging
import types
from typing import Any, Dict, List, Optional, Union, get_args, get_origin

from app.mcp.server import MCPServer, MCPTool

logger = logging.getLogger(__name__)


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


def _build_script_tool(row: Dict[str, Any]) -> Optional[MCPTool]:
    """构建 script 型工具: 本地接口数据源 + 纯数据转换脚本。"""
    import json
    from app.services.script_engine import execute_transform_script
    from app.services.local_api_client import call_local_api

    try:
        input_schema = json.loads(row.get("input_schema", "{}"))
        data_sources = json.loads(row.get("data_sources", "[]"))
    except (json.JSONDecodeError, TypeError):
        input_schema = {}
        data_sources = []

    transform_script = row.get("transform_script", "")
    script_enabled = int(row.get("script_enabled", 0)) if row.get("script_enabled") is not None else 0

    if not data_sources:
        logger.warning(f"script 型工具 {row['name']} 未配置 data_sources")
        return None

    async def script_handler(**kwargs) -> str:
        # 1. 逐个调用数据源接口（全部走 local_api_client）
        results = []
        for ds in data_sources:
            interface_id = ds.get("interface_id")
            param_mapping = ds.get("param_mapping", {})

            # 映射参数: tool参数名 → 接口参数名
            mapped_params = {}
            for tool_param, iface_param in param_mapping.items():
                if tool_param in kwargs:
                    mapped_params[iface_param] = kwargs[tool_param]
            # 注入上下文变量 ($ctx.*)
            mapped_params = _inject_context_params(mapped_params)

            from app.models.api_interface import ApiInterfaceRepository
            try:
                iface = ApiInterfaceRepository.get_by_id(interface_id)
            except Exception as e:
                results.append({"success": False, "error": f"查询接口 {interface_id} 失败: {e}"})
                continue
            if not iface:
                results.append({"success": False, "error": f"接口 {interface_id} 不存在"})
                continue

            handler_key = iface.get("local_handler", "")
            if not handler_key:
                results.append({"success": False, "error": f"接口 {interface_id} 无 local_handler"})
                continue

            result = await call_local_api(handler_key, mapped_params)
            results.append(result)

        # 2. 如果启用脚本，执行纯数据转换
        if script_enabled and transform_script.strip():
            raw = execute_transform_script(transform_script, results)
            # 尝试解析为 JSON dict，供下游卡片渲染使用
            if isinstance(raw, str):
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, dict):
                        return parsed
                except (json.JSONDecodeError, TypeError):
                    pass
            return raw

        # 3. 无脚本时，透传第一个数据源的 data 字段
        first = results[0] if results else {}
        data = first.get("data", first)
        return data if isinstance(data, (dict, list)) else str(data)

    return MCPTool(
        name=row["name"],
        description=row.get("description", ""),
        input_schema=input_schema,
        handler=script_handler,
    )


def _inject_context_params(params: dict) -> dict:
    """注入上下文变量。将 $ctx.username 等占位符替换为当前会话上下文值。"""
    from app.mcp.client import _mcp_context_var
    ctx = _mcp_context_var.get() or {}
    resolved = {}
    for key, value in params.items():
        if isinstance(value, str) and value.startswith("$ctx."):
            ctx_key = value[5:]  # 去掉 '$ctx.' 前缀
            resolved[key] = ctx.get(ctx_key, "")
        else:
            resolved[key] = value
    return resolved


def _build_tool_from_db_row(row: Dict[str, Any]) -> Optional[MCPTool]:
    """从数据库行构建 MCPTool 实例。"""
    tool_type = row.get("tool_type", "builtin")

    if tool_type == "script":
        return _build_script_tool(row)

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
        elif server is not None and cls._instance._server is not server:
            # 测试或热重启场景可能会重置 MCPServer 单例。此时 registry
            # 必须切换到调用方传入的新 server，否则工具会被加载到旧实例，
            # 新 server 的 tools/list 结果为空。
            cls._instance._server = server
            cls._instance._loaded_tool_names.clear()
        return cls._instance

    # ── 加载与重载 ────────────────────────────────────────

    def load_all_from_db(self) -> int:
        """从数据库加载所有启用的工具并注册到 MCPServer。

        Returns:
            成功加载的工具数量。
        """
        from app.models.mcp_tool import MCPToolRepository

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
