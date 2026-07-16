# 关键集成点适配

> 主文档：[README.md](./README.md) — 架构总览

---

## 九、关键集成点适配

### 9.1 user_chat.py — SSE 流式对话适配

`user_chat.py` 有两条 MCP 调用路径，script 型工具无需特殊适配即可正常工作：

| 路径 | 当前行为 | script 型兼容性 |
|------|---------|----------------|
| **路径 A**: `_chat_with_llm_tools()` | LLM Function Calling → `MCPClient.get_openai_tools()` → 多轮 tool_calls | ✅ 兼容。`MCPTool.call()` 对 script 型的 `script_handler`（返回 str，可以是纯文本或 JSON 字符串）与 builtin 型行为一致 |
| **路径 B**: `_chat_with_mcp_fallback()` | 无 API Key 语义匹配 → `MCPClient.match_tool_by_query()` | ✅ 兼容。语义匹配基于 `description` 字段，不关心 tool_type |
| **@员工调用**: `UserEmployeeInvokeHandler` | 按 `mcp_tool_ids` 过滤 → `match_tool_by_query(message, emp_id)` | ✅ 兼容。权限过滤在 MCP 工具层面，不在接口层面 |

**需注意的点**：
- script 型工具的数据源可能涉及外部 HTTP（经 `safe_http_request` 代理），耗时可能 >5s。LLM Function Calling 的 tool_calls 超时需适当放宽。
- 建议在 SSE 流中增加 `event: tool_progress` 事件，告知用户「正在查询数据…」「正在分析…」等中间状态。

### 9.2 LLM API 调用 — 唯一例外

`user_chat.py` 中的 `_call_llm_api_sync()` 调用 OpenAI 兼容 API（Chat Completions）。这类调用**不走接口管理代理**，原因：

1. LLM API 的协议（Chat Completions + SSE streaming）与通用 HTTP 接口模板不兼容
2. `api_base` 已在 `models` 表中由管理员显式配置
3. 流式响应需要长连接保持，不适合通用的请求-响应模板

**安全加固方案**（不改变调用路径，但加防护）：
```python
# user_chat.py — 在 _call_llm_api_sync() 调用前:
from app.utils.security import validate_url_safe
if not validate_url_safe(api_base)[0]:
    raise SafeHttpError(f"LLM API URL 不安全: {api_base}")
```
或者远期将 LLM API 调用也迁移为使用 `safe_http_request` 的 DNS Pinning 连接模式（需要扩展 `safe_http_request` 支持 streaming）。

### 9.3 员工工具权限过滤

权限过滤沿用 MRP 机制：`digital_employees.mcp_tool_ids` JSON 数组决定员工可使用哪些工具。
script 型工具与 builtin 型在权限过滤上**无区别**——都在 MCP 工具层面控制。

接口层（`api_interfaces`）是共享资源，不参与员工权限过滤。即：员工 A 和员工 B 都可以使用引用同一接口的不同 MCP 工具。这是合理的——接口只是数据源，权限由「谁能调用哪个 MCP 工具」决定。

### 9.4 上下文注入

`MCPClient._inject_context()` 向工具注入 `username` 等会话上下文。script 型工具的 `_inject_context_params()` 支持 `$ctx.username` 等占位符语法：

```json
// data_sources param_mapping 示例
{
  "interface_id": 10,
  "param_mapping": {
    "username": "$ctx.username",
    "keyword": "keyword"
  }
}
```

该占位符对本地接口和代理接口同样有效。

> 实现代码见：[MCP 注册中心改造 — `_inject_context_params()`](./04-mcp-registry-refactor.md#62-新-registry--_build_tool_from_db_row-增加-script-分支)

### 9.5 与 register_all_tools() 的关系

MRP 的 `register_all_tools()` 调用 `MCPToolRegistry.load_all_from_db()`，后者遍历 `mcp_tools` 表中所有 `is_enabled=1` 的记录。新增 `tool_type='script'` 后，`_build_tool_from_db_row` 自动分发到 `_build_script_tool()`——**无需修改 `load_all_from_db` 或 `register_all_tools`**。热重载同样自动覆盖。

### 9.6 网络层防火墙配合

实施本方案后，可在操作系统/容器层面配置出站防火墙规则：

```
# 仅允许接口管理服务进程访问外网
# Windows Firewall / iptables 示例思路:
Allow: python.exe → 0.0.0.0/0:443 (仅 safe_http_request 使用)
Deny:  python.exe → 0.0.0.0/0:*   (其他所有出站)
Deny:  python.exe → 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16 (内网)
```

结合 `safe_http_request` 的 DNS Pinning + SSRF 校验，形成纵深防御。

---

> 相关文档：[本地接口层设计](./02-local-api-layer.md) | [MCP 注册中心改造](./04-mcp-registry-refactor.md) | [迁移计划](./08-migration-plan.md)
