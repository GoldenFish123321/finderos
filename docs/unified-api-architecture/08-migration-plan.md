# 迁移计划 & 兼容策略

> 主文档：[README.md](./README.md) — 架构总览

---

## 十、迁移计划

> **前置条件**: MRP（mcp_refactor_plan.md）全部 Phase 已完成，`mcp_tools` 表、管理后台、员工工具选择器已上线。

### Phase 1: 数据层准备（1天）

| 步骤 | 内容 |
|------|------|
| 1.1 | `api_interfaces` 表：放宽 `api_url` 约束 + 新增 `interface_type`, `is_system`, `local_handler`, `response_content_type` 列 |
| 1.2 | `mcp_tools` 表：新增 `data_sources`, `transform_script`, `script_enabled` 列 |
| 1.3 | 编写迁移脚本 `migrate_db.py` |

> 详细 Schema 见：[数据库变更方案](./01-database-schema.md)

### Phase 2: 本地接口注册表 + 外部代理（1.5天）

| 步骤 | 内容 |
|------|------|
| 2.1 | 实现 `local_api_client.py`：函数注册表 + `_init_local_handlers()` + `_register_external_proxies()` + `call_local_api()` |
| 2.2 | 实现 `local_api_registry.py`：18 个种子数据 + `sync_local_api_interfaces()` |
| 2.3 | 在 `main.py` 启动流程中按顺序调用：`_init_local_handlers()` → `sync_local_api_interfaces()` → `_register_external_proxies()` → `load_all_from_db()` |
| 2.4 | 为瞭望采集源、音乐 API 等在 `api_interfaces` 创建 external 记录（含 `response_content_type='html'`） |

> 详细设计见：[本地接口层设计](./02-local-api-layer.md)

### Phase 3: 脚本引擎（1天）

| 步骤 | 内容 |
|------|------|
| 3.1 | 实现 `script_engine.py`：收紧的 AST 白名单校验（禁 import）+ 受限执行（返回 str）+ 超时保护 |
| 3.2 | 实现脚本在线测试 API（`POST /admin/mcp/tool/test-script`） |
| 3.3 | 预置脚本模板（天气格式化、数据概览、音乐推荐等） |

> 详细设计见：[脚本执行引擎](./03-script-engine.md)

### Phase 4: MCP 注册中心改造（1天）

| 步骤 | 内容 |
|------|------|
| 4.1 | `registry.py`：新增 `_build_script_tool()` —— 所有数据源统一调 `call_local_api()` |
| 4.2 | `_build_tool_from_db_row()`：增加 `if tool_type == 'script'` 分支 |
| 4.3 | 实现 `_inject_context_params()` 上下文注入 |
| 4.4 | 创建示例 script 型工具（天气、音乐），验证端到端代理流程 |

> 详细设计见：[MCP 注册中心改造](./04-mcp-registry-refactor.md)

### Phase 5: 前端适配（2天）

| 步骤 | 内容 |
|------|------|
| 5.1 | 接口管理列表：增加 external/local Tab + 类型徽章 |
| 5.2 | 接口表单：local 型只读视图；external 型增加 response_content_type 选择 |
| 5.3 | MCP 工具表单：tool_type 下拉新增 `script`；数据源选择器（仅列 local 接口，含代理） + 脚本编辑器 |
| 5.4 | 脚本编辑器：textarea + 语法高亮（可选 CodeMirror） |
| 5.5 | 脚本测试按钮：输入参数 → 查看本地接口调用耗时 → 查看脚本字符串输出 |

> 详细设计见：[前端管理界面设计](./05-frontend-design.md)

### Phase 6: 安全加固 + 文档（1天）

| 步骤 | 内容 |
|------|------|
| 6.1 | `registry.py` 中 `api` 型工具的 `urllib.request.urlopen()` 迁移为 `safe_http_request()` |
| 6.2 | `user_chat.py` 中 LLM API 调用增加 `validate_url_safe()` 前置校验 |
| 6.3 | `entertainment_tools.py` 音乐工具：硬编码 URL 迁移到 `api_interfaces` external 记录 |
| 6.4 | 更新 `docs/design.md`、`docs/api.md`、`README.md` |
| 6.5 | 部署网络层防火墙规则（仅允许 safe_http_request 进程访问外网） |

> 详细设计见：[关键集成点适配](./07-integration-points.md)

---

## 十一、兼容策略

```
实施后四种 tool_type 共存:
  - tool_type='builtin':   保持 MRP 的 handler_module + importlib 路径
  - tool_type='api':        保持 MRP 的 api_url + urllib 路径（远期加固为 safe_http_request）
  - tool_type='crawl4ai':   保持 MRP 的爬虫路径
  - tool_type='script':     新增 data_sources（仅 local 接口）+ transform_script（纯数据→str）路径

远期（v0.7.0+）可选迁移:
  - 音乐工具: builtin 版（硬编码 api.injahow.cn）→ 在 api_interfaces 注册 external → 自动代理 → script 型
  - 瞭望采集: builtin 版（直接 urllib.request）→ 采集源注册为 external → call_local_api('proxy/{id}') 获取 HTML
  - API 型员工: 直接 urllib.request → api_interfaces 代理模式
  - builtin_tools/ 目录不删除（MRP 已投入拆分工作，保留价值）
```

---

> 相关文档：[数据库变更方案](./01-database-schema.md) | [文件变更清单](./06-file-changes.md)
