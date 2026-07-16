# MCP 工具注册中心改造

> 主文档：[README.md](./README.md) — 架构总览

---

## 六、MCP 工具注册中心改造

### 6.1 新旧对比

| 维度 | 旧架构 (v0.10, MRP 保持) | 新增能力 |
|------|--------------------------|-------------------|
| 工具类型 | `builtin` / `api` / `crawl4ai` | 新增 `script` 型（与三种旧类型**共存**） |
| builtin 型 | Python 函数指针 (`handler_module`) → importlib 加载 | **保持不动** |
| api 型 | `api_url` + `api_headers` → 直接 HTTP 调用 | **远期建议迁移到 api_interfaces 代理模式** |
| script 型 | 不存在 | `data_sources`（仅引用 local 接口，含代理外部API）+ `transform_script`（纯数据→字符串） |
| 音乐工具 | `builtin` 型（代码中硬编码 `api.injahow.cn`） | 可选迁移为 script 型：在 api_interfaces 注册 external → 自动代理为 local → 脚本格式化 |
| 天气工具 | API 型数字员工 | 可选新增 script 型 MCP 工具（同上代理模式） |
| 瞭望采集 | `builtin` 型（直接 urllib.request） | 迁移为：采集源注册为 external 接口 → 自动代理为 local → collect_tools 调 call_local_api 获取 HTML → 自行解析 |
| 注册方式 | MRP 统一的 `_build_tool_from_db_row` → 按 tool_type 分支 | 新增 `script` 分支，所有数据源调 `call_local_api()`（统一 local 接口） |
| 热重载 | 重新读数据库 + importlib | script 型仅需重新读数据库（脚本和接口配置都在 DB 中） |

### 6.2 新 Registry — `_build_tool_from_db_row()` 增加 `script` 分支

```python
# app/mcp/registry.py — 在现有 _build_tool_from_db_row 中新增 script 分支

def _build_tool_from_db_row(row: Dict[str, Any]) -> Optional[MCPTool]:
    """从数据库行构建 MCPTool。新增 script 型分支。"""
    import json

    tool_type = row.get("tool_type", "builtin")

    # ── 新增分支: script 型 ──
    if tool_type == "script":
        return _build_script_tool(row)

    # ── 以下为 MRP 原有逻辑（保持不变）──
    if tool_type == "builtin":
        return _build_builtin_tool(row)       # handler_module + importlib
    elif tool_type == "api":
        return _build_api_tool(row)            # api_url + urllib
    elif tool_type == "crawl4ai":
        return _build_crawl4ai_tool(row)

    return None


def _build_script_tool(row: Dict[str, Any]) -> Optional[MCPTool]:
    """构建 script 型工具: 本地接口数据源 + 纯数据转换脚本。

    关键约束:
    - data_sources 中的 interface_id 只能指向 interface_type='local' 的记录
      （external 接口已在启动时自动包装为虚拟 local handler，见 02-local-api-layer.md §4.5）
    - 所有数据源统一通过 call_local_api() 调用，不区分内外
    - 脚本返回字符串（可以是纯文本或 JSON 字符串），直接作为 MCP text content
    """
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
    script_enabled = bool(row.get("script_enabled", 0))

    if not data_sources:
        logger.warning(f"script 型工具 {row['name']} 未配置 data_sources")
        return None

    async def script_handler(**kwargs) -> str:
        """script 型统一处理器: 调用本地接口 → 脚本转换 → 返回字符串。"""
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

            # 统一通过 local_handler 调用（无论原始是 local 还是 external 代理）
            from app.models.api_interface import ApiInterfaceRepository
            iface = ApiInterfaceRepository.get_by_id(interface_id)
            if not iface:
                results.append({"success": False, "error": f"接口 {interface_id} 不存在"})
                continue

            handler_key = iface.get("local_handler", "")
            if not handler_key:
                results.append({"success": False, "error": f"接口 {interface_id} 无 local_handler"})
                continue

            result = await call_local_api(handler_key, mapped_params)
            results.append(result)

        # 2. 如果启用脚本，执行纯数据转换（返回 str，可以是纯文本或 JSON 字符串）
        if script_enabled and transform_script.strip():
            return execute_transform_script(transform_script, results)

        # 3. 无脚本时，透传第一个数据源的 data 字段的字符串表示
        first = results[0] if results else {}
        data = first.get("data", first)
        return str(data) if not isinstance(data, str) else data

    return MCPTool(
        name=row["name"],
        description=row.get("description", ""),
        input_schema=input_schema,
        handler=script_handler,  # 返回 str（纯文本或 JSON 字符串），MCPServer.call_tool 自动包装为 text content
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
```

### 6.3 本地接口调用客户端

`call_local_api(handler_key, params)` 基于 `_LOCAL_HANDLER_MAP` 函数注册表，通过进程内函数直调实现，零网络开销。`handler_key` 对应 `api_interfaces.local_handler` 字段。

> 详细实现见：[本地接口层设计 — §4.3 函数注册表](./02-local-api-layer.md#43-函数注册表--本地接口客户端)

---

> 相关文档：[本地接口层设计](./02-local-api-layer.md) | [脚本执行引擎](./03-script-engine.md) | [关键集成点](./07-integration-points.md)
