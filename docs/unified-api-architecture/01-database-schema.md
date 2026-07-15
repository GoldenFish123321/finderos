# 数据库变更方案

> 主文档：[README.md](./README.md) — 架构总览

---

## 三、数据库变更方案

### 3.1 修改表: `api_interfaces` — 新增接口类型

```sql
-- 新增字段
ALTER TABLE api_interfaces ADD COLUMN interface_type TEXT DEFAULT 'external';
-- 'external' = 外部接口（管理员可增删改）
-- 'local'    = 本地接口（系统内置，不可修改/不可删除）

ALTER TABLE api_interfaces ADD COLUMN is_system INTEGER DEFAULT 0;
-- 1 = 系统内置，前端隐藏编辑/删除按钮

ALTER TABLE api_interfaces ADD COLUMN local_handler TEXT DEFAULT '';
-- 本地接口的内部处理器标识，如 'warehouse/search'
-- interface_type='local' 时指向 _LOCAL_HANDLER_MAP 的键
-- interface_type='external' 时留空（系统自动生成虚拟 handler）

ALTER TABLE api_interfaces ADD COLUMN response_content_type TEXT DEFAULT 'json';
-- 响应内容的 MIME 类型提示: 'json' / 'html' / 'text'
-- 'json': safe_http_request 返回后尝试 json.loads（默认）
-- 'html': 跳过 JSON 解析，返回原始 HTML 文本（瞭望采集等场景）
-- 'text': 返回纯文本
```

修改后 `api_interfaces` 表核心字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| name | TEXT UNIQUE | 接口名称 |
| description | TEXT | 描述 |
| **interface_type** | TEXT | `external` / `local` |
| **is_system** | INTEGER | 系统内置 (0/1)，local 型自动为 1 |
| **local_handler** | TEXT | 本地接口处理器路由（external 型留空，由系统自动生成 `proxy/{id}`） |
| **response_content_type** | TEXT | 响应类型：`json`（默认）/ `html` / `text` |
| api_url | TEXT | 外部接口 URL（external 型必填，local 型填 `local://`） |
| api_method | TEXT | HTTP 方法 |
| api_headers | TEXT | 请求头 JSON |
| api_params_template | TEXT | 参数模板 |
| response_render_template | TEXT | 响应渲染模板（可为空，由脚本替代） |
| api_secret | TEXT | 密钥(加密存储) |
| is_enabled | INTEGER | 启用状态 |
| sort_order | INTEGER | 排序 |

### 3.2 修改表: `mcp_tools` — 新增 script 型字段

```sql
-- 新增字段
ALTER TABLE mcp_tools ADD COLUMN data_sources TEXT DEFAULT '[]';
-- JSON 数组，每个元素: { interface_id, param_mapping }
-- 约束: interface_id 只能指向 interface_type='local' 的记录
--       （external 接口在启动时已自动包装为虚拟 local handler）
-- 例: [{"interface_id": 1, "param_mapping": {"city": "city"}}]

ALTER TABLE mcp_tools ADD COLUMN transform_script TEXT DEFAULT '';
-- 自定义 Python 转换脚本（纯数据转换，不能 import，不能访问外网）
-- 脚本签名: def transform(data_sources: list[dict]) -> str

ALTER TABLE mcp_tools ADD COLUMN script_enabled INTEGER DEFAULT 0;
-- 是否启用脚本转换（无脚本时直接透传第一个接口的 data 字段作为字符串）

-- 以下 MRP 字段保留不动（builtin/api/crawl4ai 型继续使用）:
--   handler_module   → builtin 型仍然使用
--   api_url          → api 型仍然使用（远期建议迁移到 api_interfaces）
--   api_method       → 同上
--   api_headers      → 同上
--   tool_type        → 新增 'script' 选项，四种类型共存
```

修改后 `mcp_tools` 表核心字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| name | TEXT UNIQUE | 工具唯一标识 |
| display_name | TEXT | 显示名称 |
| description | TEXT | 工具描述（供 LLM 理解） |
| category | TEXT | 分类 |
| **tool_type** | TEXT | 保留 MRP 三分类 + 新增 `script` 型（共存） |
| **data_sources** | TEXT | JSON 数组：接口数据源配置 |
| **transform_script** | TEXT | 转换脚本（Python 代码） |
| **script_enabled** | INTEGER | 是否启用脚本 |
| input_schema | TEXT | JSON Schema 参数定义 |
| output_schema | TEXT | 输出 Schema |
| is_enabled | INTEGER | 启用/禁用 |
| is_system | INTEGER | 系统内置 |
| sort_order | INTEGER | 排序 |
| config | TEXT | 额外配置 JSON |

### 3.3 迁移策略

```
Phase 1 — 数据迁移（注意 SQLite 限制）:
  1. api_interfaces 表: 放宽 api_url 约束（NOT NULL → DEFAULT ''），新增
     interface_type / is_system / local_handler / response_content_type 列
     （SQLite 不支持 ALTER COLUMN，需建新表→迁移数据→删旧表→重命名，同一事务）
  2. mcp_tools 表: 新增 data_sources / transform_script / script_enabled 列
  3. 现有 external 接口: 回填 interface_type='external', response_content_type='json'
  4. 为 18 个 builtin 函数创建对应的 local 接口记录 (interface_type='local', is_system=1)
  5. 音乐 API 等在 api_interfaces 中创建 external 记录

Phase 2 — 代码重构:
  1. 实现 local_api_client.py: 函数注册表 + _init_local_handlers() +
     _register_external_proxies()（external → 虚拟 local handler）
  2. 实现 local_api_registry.py: 种子数据 + sync_local_api_interfaces()
  3. 实现 script_engine.py: 收紧的 AST 白名单沙箱（禁 import，纯数据转换，返回 str）
  4. 改造 registry.py: _build_tool_from_db_row() 新增 script 分支，所有数据源统一调 call_local_api()

Phase 3 — 前端适配:
  1. 接口管理列表区分 external / local 标签；local 型只读视图
  2. MCP 工具编辑页: tool_type 下拉增加 'script'；条件渲染数据源选择器 + 脚本编辑器
  3. 脚本测试按钮: 输入参数 → 查看各本地接口调用耗时 → 查看脚本字符串输出
```

---

> 相关文档：[本地接口层设计](./02-local-api-layer.md) | [迁移计划](./08-migration-plan.md)
