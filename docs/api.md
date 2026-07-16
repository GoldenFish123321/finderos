# API 接口文档 v1.0.0-beta

> 基础 URL: `http://localhost:10010`
> 认证方式: Tornado Secure Cookie（登录后自动携带）
> CSRF: 所有 POST 请求需携带 `_xsrf` token

---

## 一、认证

### POST / — 用户登录
- **Content-Type**: `application/x-www-form-urlencoded`
- **参数**: `username`, `password`
- **成功**: 302 跳转到 `/chat`，后台和模型 API 配置入口由页面链接按权限进入
- **失败**: 渲染登录页 + 错误提示
- **限速**: 同 IP+用户名 5次/15分钟

### POST /register — 用户注册
- **Content-Type**: `application/x-www-form-urlencoded`
- **参数**: `username`, `password`, `password_confirm`
- **成功**: 自动登录并 302 跳转到 `/chat`
- **失败**: 渲染注册页 + 错误提示（用户名已存在 / 密码不一致 / 密码强度不足等）

### GET /register — 注册页面
- 渲染 `register.html` 注册表单页面

### GET /logout — 登出
- 清除 Cookie，302 跳转到 `/`

---

## 二、管理后台

> 所有 `/admin/*` 接口需要后台功能权限（`AdminBaseHandler.prepare()` 校验角色是否关联后台功能，非硬编码角色名）

### 2.1 仪表盘

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin` | 后台首页，显示统计卡片 |

### 2.2 用户管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/user` | 用户列表（?page=1&search=关键词） |
| GET | `/admin/user/add` | 新增用户表单 |
| GET | `/admin/user/edit?id=` | 编辑用户表单 |
| POST | `/admin/user/add` | 保存新用户 |
| POST | `/admin/user/edit` | 更新用户 |
| POST | `/admin/user/delete` | 删除用户 (id) |
| POST | `/admin/user/toggle` | 启用/禁用切换 (id) |

### 2.3 角色管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/role` | 角色列表 |
| GET/POST | `/admin/role/add` | 新增角色 |
| GET/POST | `/admin/role/edit` | 编辑角色 |
| POST | `/admin/role/delete` | 删除角色 (id) |

### 2.4 功能管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/function` | 功能列表（树形） |
| GET/POST | `/admin/function/add` | 新增功能 |
| GET/POST | `/admin/function/edit` | 编辑功能 |
| POST | `/admin/function/delete` | 删除功能 (id) |
| POST | `/admin/function/toggle` | 启用/禁用 (id) |

### 2.5 菜单管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/menu` | 菜单配置页（角色→功能→菜单映射） |

---

## 三、瞭望采集

### 3.1 瞭望采集主页

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/watch` | 瞭望采集页（?keyword=&page=&source_id=） |
| POST | `/admin/watch` | **执行采集** → JSON 响应 |
| GET | `/admin/watch/stream` | **SSE 实时采集进度**（有副作用，需携带 `_xsrf`） |
| GET | `/admin/watch/log` | 采集日志页（从 `audit_logs` 读取 `*COLLECT*` 记录） |

#### POST /admin/watch 请求参数

> **Content-Type**: `application/x-www-form-urlencoded`

| 参数 | 类型 | 说明 |
|------|------|------|
| `keyword` | string | 搜索关键词 |
| `source_ids` | string | 瞭源ID列表，逗号分隔；为空则使用所有启用的瞭源。兼容 jQuery 数组语法 `source_ids[]=1&source_ids[]=2` |

#### POST /admin/watch 响应

```json
{
  "code": 0,
  "msg": "采集完成，共获取 15 条新闻",
  "news": [
    {
      "id": 1,
      "title": "新闻标题",
      "link": "https://...",
      "summary": "摘要...",
      "source_name": "百度新闻"
    }
  ],
  "results": [...],
  "total": 15
}
```

#### GET /admin/watch/stream SSE 事件

> 查询参数：`keyword`、`source_ids`、`_xsrf`。虽然使用 GET/EventSource，但会触发采集和写库，因此服务端手动执行 XSRF 校验。

```text
event: collect_progress
data: {"percent":50,"current_url":"https://...","success":1,"failed":0,"message":"已完成 1/2"}

event: collect_done
data: {"code":0,"msg":"采集完成，共获取 15 条新闻","news":[...],"total":15,"success":2,"failed":0}

event: collect_error
data: {"code":1,"msg":"请输入关键词"}
```

### 3.2 保存到数据仓库

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/admin/watch/save` | 保存选中结果 (result_ids) |

### 3.3 瞭源管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/watch/source` | 瞭源列表 |
| GET/POST | `/admin/watch/source/add` | 新增瞭源 |
| GET/POST | `/admin/watch/source/edit` | 编辑瞭源 |
| POST | `/admin/watch/source/delete` | 删除瞭源 |
| POST | `/admin/watch/source/toggle` | 启用/禁用瞭源 |

### 3.4 数据仓库

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/warehouse` | 数据仓库列表（?page=&keyword=&source_id=） |
| GET | `/admin/warehouse/detail?id=` | 查看详情 |
| POST | `/admin/warehouse/delete` | 删除记录 (id) |
| POST | `/admin/warehouse/batch-delete` | 批量删除 (ids) |

---

## 四、模型引擎

### 4.1 模型管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/model` | 模型引擎列表（?page=&category=） |
| GET/POST | `/admin/model/config` | 模型 API 快速配置（普通用户默认权限，API Key 密码框回显且可显示/隐藏，不含删除/启停/设默认） |
| POST | `/admin/model/config/test` | 测试模型 API 配置连通性；请求体同快速配置表单，返回 `code/msg/status/elapsed_ms` |
| GET/POST | `/admin/model/add` | 新增模型 |
| GET/POST | `/admin/model/edit` | 编辑模型 |
| POST | `/admin/model/delete` | 删除模型 |
| POST | `/admin/model/toggle` | 启用/禁用 |
| POST | `/admin/model/default` | 设为默认模型 |

> 安全约束：快速配置页修改 Provider、API Base 或 Model Name 时，必须重新输入新 API Key，或显式勾选确认复用当前密钥，避免旧密钥被误发送到新的接口地址。

### 4.2 模型对话 (SSE) — ⚠️ 已废弃

> **v0.4 起已废弃**：后台模型对话功能已统一迁移至前台 `/chat/stream`（MCP 架构）。
> 请使用 [七、用户前台-智能问数](#七用户前台-智能问数v030) 中的 `/chat/stream` 端点。

### 4.3 模型 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/api/model/list` | JSON 格式模型列表（?page=&limit=&category=）。仅返回已启用模型（`is_enabled=1`） |

### 4.4 Token 消耗说明

- Token 消耗通过 `/chat/stream` 对话自动累加到 `ai_models.total_tokens`
- `migrate_db.py` 提供 `ai_models.total_tokens` 列的 DDL 迁移（v0.2），不涉及跨表数据搬运

---

## 五、已省略的补充端点

> 以下端点在前面章节中未列出，在此补充。

### 5.1 用户管理（补充）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/admin/user/batch-delete` | 批量删除用户 (ids) |
| POST | `/admin/user/batch-toggle` | 批量启用/禁用 (ids, enable) |
| GET/POST | `/admin/user/change-password` | 修改密码 |

### 5.2 菜单管理（补充）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/admin/menu/sort` | 菜单排序（上移/下移） |

### 5.3 瞭望采集（补充）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/admin/watch/deep-collect` | 一站式深度采集 |

### 5.4 数据仓库（补充）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/admin/warehouse/deep-collect` | 深度采集指定仓库记录 |

---

## 六、数字化员工（v0.3）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/employee` | 员工列表（卡片式，?page=&type=） |
| GET | `/admin/employee/add` | 新增员工页面 |
| POST | `/admin/employee/add` | 提交新增员工 |
| GET | `/admin/employee/edit?id=` | 编辑员工页面 |
| POST | `/admin/employee/edit` | 提交编辑员工 |
| POST | `/admin/employee/delete` | 删除员工 |
| POST | `/admin/employee/toggle` | 启用/禁用员工 |
| POST | `/admin/employee/invoke` | **SSE 流式调用员工** |
| GET | `/admin/api/employee/list` | 员工 JSON API |
| GET | `/admin/employee/test` | 员工对话测试页 |

---

## 七、用户前台-智能问数（v0.3）

### 7.1 对话页面与流式 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/chat` | 用户前台 A/B/C/D/E 五区对话主页；拥有 `/admin/model/config` 权限时，侧边栏与欢迎页提供模型 API 配置入口 |
| POST | `/chat/stream` | **SSE 流式 AI 对话**（含 MCP Function Calling） |
| POST | `/chat/employee/invoke` | **SSE 流式 @数字员工调用** |

#### POST /chat/stream 请求参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `model_id` | int | 是 | 使用的 AI 模型 ID |
| `message` | string | 是 | 用户消息内容 |
| `conversation_id` | int | 否 | 对话 ID（多轮对话上下文） |

#### POST /chat/employee/invoke 请求参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `employee_id` | int | 是 | 数字员工 ID |
| `message` | string | 是 | 用户消息内容（含 @员工名） |

### 7.2 前台 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/chat/models` | 获取可用模型列表（JSON）。仅返回已启用模型（`is_enabled=1`），字段：`id`, `name`, `provider`, `model_name`, `category`, `is_default` |
| GET | `/api/chat/employees` | 获取数字员工列表（JSON） |

### 7.3 对话管理 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/chat/conversation/list` | 当前用户对话历史列表 |
| POST | `/api/chat/conversation/create` | 创建新对话 |
| POST | `/api/chat/conversation/delete` | 删除对话（body 参数 `id`） |
| GET | `/api/chat/conversation/messages` | 获取对话消息（?id=） |

### 7.3b 管理侧会话管理 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/conversation` | 管理员查看所有用户会话，支持 `username`、`keyword`、`page`、`id` 查询 |
| POST | `/admin/conversation/delete` | 管理员删除任意会话及其消息（body 参数 `id`，需 `_xsrf`） |

### 7.4 TTS 语音合成 API（v0.9）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/chat/tts` | **Edge TTS 语音合成**，返回 MP3 音频流 |

#### POST /api/chat/tts 请求参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `text` | string | 是 | 待合成文本（1-4000 字符） |
| `voice` | string | 否 | 语音名称，默认 `zh-CN-XiaoxiaoNeural`（晓晓） |

#### 可用语音

| 语音 ID | 名称 | 风格 |
|---------|------|------|
| `zh-CN-XiaoxiaoNeural` | 晓晓 | 女声，活泼（默认） |
| `zh-CN-YunxiNeural` | 云希 | 男声，青年 |
| `zh-CN-YunjianNeural` | 云健 | 男声，中年 |
| `zh-CN-XiaoyiNeural` | 晓伊 | 女声，温柔 |
| `zh-CN-YunyangNeural` | 云扬 | 男声，新闻播报 |
| `zh-CN-XiaochenNeural` | 晓晨 | 女声，自然 |

#### 响应

- **成功**：`Content-Type: audio/mpeg`，返回 MP3 二进制音频流
  - 响应头 `X-TTS-Voice`: 使用的语音名称
  - 响应头 `X-TTS-Cached`: 是否命中缓存（`true`/`false`）
- **失败**：HTTP 400/500，返回 JSON `{"code": 1, "msg": "错误描述"}`

#### 缓存机制

- 基于 `MD5(text + voice)` 的本地文件缓存
- 缓存目录：系统临时目录 `/finderos_tts/`
- 相同文本 + 语音不重复生成，永久缓存
- 生成失败自动清理损坏的缓存文件

---

## 八、接口管理（Issue #26）

### 8.1 管理侧接口模板

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/interface` | 接口模板列表（`?page=&keyword=`） |
| GET/POST | `/admin/interface/add` | 新增接口模板 |
| GET/POST | `/admin/interface/edit` | 编辑接口模板（`?id=`） |
| POST | `/admin/interface/delete` | 删除接口模板 |
| POST | `/admin/interface/toggle` | 启用/禁用接口模板 |
| POST | `/admin/interface/test` | 测试接口模板（支持保存接口或表单草稿配置） |
| GET | `/admin/api/interface/list` | 获取已启用接口模板，供 API 型数字员工联动 |

### 8.2 接口测试

请求可传已保存接口 `id + message`，也可提交表单草稿字段：

```json
{
  "api_url": "https://wttr.in/{message}?format=j1",
  "api_method": "GET",
  "api_headers": "{\"Accept\":\"application/json\"}",
  "api_params_template": "",
  "message": "成都"
}
```

响应包含 `code`、`status`、`elapsed_ms`、`headers`、`raw` 与可解析的 `data`。安全约束：仅允许 `http/https`，Headers 必须是 JSON 对象且不得包含 CR/LF；接口测试不自动跟随 30x 重定向，并使用已校验的 DNS 解析 IP 发起请求。

### 8.3 数字员工联动

API 型数字员工新增/编辑页可通过 `api_interface_id` 选择接口模板，自动填充 URL / Method / Headers / Params / Response Template。接口密钥不通过列表 API 回显；`Authorization`、`Cookie`、`X-API-Key` 等敏感 Header 以 `******` 脱敏展示，提交未修改的脱敏值时服务端保留原始 Header。

---

## 九、MCP 工具管理（v0.10）

### 9.1 管理侧

> 访问控制：MCP 工具管理需要角色拥有 `/admin/mcp/tool` 功能权限；普通用户默认只拥有 `/admin/model/config`，因此默认不能进入 MCP 工具管理页。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/mcp/tool` | MCP 工具列表（分页） |
| GET/POST | `/admin/mcp/tool/add` | 新增 MCP 工具 |
| GET/POST | `/admin/mcp/tool/edit` | 编辑 MCP 工具（`?id=`） |
| POST | `/admin/mcp/tool/delete` | 删除 MCP 工具 |
| POST | `/admin/mcp/tool/toggle` | 启用/禁用 MCP 工具 |
| POST | `/admin/mcp/tool/test` | 在线测试 MCP 工具 |
| GET | `/admin/mcp/tool/test-logs` | 获取工具测试日志（`?id=`） |
| POST | `/admin/mcp/reload` | 热重载所有 MCP 工具 |

### 9.1b 使用流程

1. 在 `/admin/mcp/tool` 确认工具“已启用”。
2. 点“测试”，按 Input Schema 提交 JSON 参数。
3. 修改工具后调用 `POST /admin/mcp/reload` 热重载，使配置进入 MCP Server。
4. 在数字员工编辑页勾选“MCP 工具权限”，否则员工不会获得该工具能力。
5. 仅配置大模型 API 时使用 `/admin/model/config`；普通用户默认具备该权限。

HTTP API 型工具支持 `api_url` 中的 `{参数名}` 占位符。GET 请求会把未出现在 URL 占位符中的参数追加到 query string；POST 请求会发送 JSON body。

### 9.2 MCP 工具分类

| 分类 | 说明 | 工具数量 |
|------|------|---------|
| warehouse | 数据仓库搜索/统计/全文检索 | 4 |
| collect | 瞭望采集/深度采集/瞭望源列表 | 3 |
| employee | 数字员工列表/调用 | 2 |
| model | AI 模型列表/默认模型 | 2 |
| chat | 对话历史/消息查询 | 2 |
| entertainment | 随机音乐推荐 | 1 |
| crawl4ai | Crawl4ai 智能/批量采集 | 2 |
| system | 技能加载/系统统计 | 2 |

### 9.3 数字员工 MCP 工具权限

- 数字员工新增/编辑页支持多选 MCP 工具（按分类组织）
- 未配置工具时遵循**最小权限原则**：员工无权调用任何 MCP 工具
- `crawl4ai_enabled` 字段已废弃，改为通过 MCP 工具 `collect_with_crawl4ai` 控制

---

## 十、默认用户权限

| 角色 | 默认功能路由 | 说明 |
|------|-------------|------|
| 系统管理员 | 所有启用功能 | 拥有全部后台功能 |
| 普通用户 | `/admin/model/config` | 可进入模型 API 快速配置页；其它后台模块需额外授权 |

后台访问使用路由级 RBAC：`/admin/model/config` 仅覆盖模型 API 快速配置入口，不会放行 `/admin/model/add`、`/admin/model/edit`、`/admin/user`、`/admin/mcp/tool` 等其它功能路由。

---

## 十一、技能管理（v0.10 更新）

### 11.1 管理侧

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/skill` | 技能列表（分页） |
| GET/POST | `/admin/skill/add` | 新增技能（支持绑定 MCP 工具） |
| GET/POST | `/admin/skill/edit` | 编辑技能（`?id=`） |
| POST | `/admin/skill/delete` | 删除技能 |
| POST | `/admin/skill/toggle` | 启用/禁用技能 |

### 11.2 技能类型

- **纯 Prompt 型**：不绑定 MCP 工具，仅提供文本指令模板
- **MCP 工具绑定型**（v0.10 新增）：通过 `mcp_tool_id` 关联 MCP 工具

### 11.3 三色徽章体系

员工列表页中技能标签按类型区分颜色：
- 🔧 **蓝色徽章** (`.mcp-tag`)：MCP 工具
- ⭐ **绿色徽章** (`.skill-tag`)：新格式 Skill
- 📋 **橙黄徽章** (`.legacy-tag`)：旧格式 TAG（兼容过渡）
