> 文档版本: v{{ app_version }}
> 最后更新: 2026-07-15

## 1. 项目概述

「瞭望与问数系统」是一个轻量级的智能数据采集与 AI 问数平台，基于 Python Tornado 框架构建。
核心能力包括：
- 🔐 **用户认证与 RBAC 权限管理**
- 🔭 **瞭望采集**：可配置的 Web 数据采集引擎（默认百度新闻、搜狗搜索、Bing RSS 三源）
- 🗄️ **数据仓库**：采集结果的统一存储与检索（FTS5 全文检索）
- 🤖 **模型引擎**：OpenAI 范式多 Provider AI 模型的接入管理与流式对话，支持 text/image/video 等多分类
- 🖼️ **媒体生成**：AI 文生图/图生图/文生视频/图生视频，SSE 卡片渲染，视频本地代理缓存
- 🔒 **信任边界**：外部媒体请求使用 DNS 固定客户端，舆情会话摘要按角色脱敏
- ⚙️ **运维配置**：17 项系统配置均经白名单和数值范围校验
- 🧠 **MCP 协议**：数据库驱动的 20 个工具注册中心（builtin_tools/ 自动发现），支持热重载和在线测试
- 💬 **智能问数**：用户前台 SSE 流式对话，支持 MCP 工具调用
- 🧑‍💼 **数字员工**：LLM 型 / API 型，支持 MCP 工具权限精细控制（最小权限原则）
- 🎯 **技能管理**：纯 Prompt 模板库，LLM 按需加载，支持绑定 MCP 工具
- 🏷️ **三色徽章系统**：MCP 工具（蓝）、Skill（绿）、旧 TAG（橙黄）视觉区分

## 2. 技术架构

```
┌──────────────────────────────────────────────────────────┐
│                    Browser (Layui 2.x + ECharts 5.x)     │
├──────────────────────────────────────────────────────────┤
│                   Tornado HTTP Server                    │
│  ┌──────────┐ ┌──────────┐ ┌────────────┐ ┌───────────┐ │
│  │ Auth     │ │ Admin    │ │ Chat/SSE   │ │ MCP Tools │ │
│  │ Handlers │ │ Handlers │ │ Handlers   │ │ Handlers  │ │
│  └────┬─────┘ └────┬─────┘ └─────┬──────┘ └─────┬─────┘ │
│       │             │             │              │       │
│  ┌────┴─────────────┴─────────────┴──────────────┴─────┐ │
│  │                Services Layer                        │ │
│  │  ┌──────────────┐ ┌────────────┐ ┌───────────────┐  │ │
│  │  │ collector.py │ │ security   │ │ scheduler.py  │  │ │
│  │  │ 采集+解析    │ │ SSRF+审计  │ │ 定时采集调度   │  │ │
│  │  └──────────────┘ └────────────┘ └───────────────┘  │ │
│  │  ┌──────────────────┐                               │ │
│  │  │ deep_collector   │                               │ │
│  │  │ 深度采集+正文提取 │                               │ │
│  │  └──────────────────┘                               │ │
│  │  ┌──────────────────────────────────────────────┐    │ │
│  │  │          MCP Layer (app/mcp/)                 │    │ │
│  │  │  Server · Client · Tools · OpenAI 格式适配    │    │ │
│  │  └──────────────────────────────────────────────┘    │ │
│  └─────────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────┐ │
│  │           Repository Layer (Models)                  │ │
│  │  UserRepo / RoleRepo / FunctionRepo /               │ │
│  │  WatchSourceRepo / WatchResultRepo /                │ │
│  │  DataWarehouseRepo / AiModelRepo /                  │ │
│  │  ConversationRepo / DigitalEmployeeRepo             │ │
│  └──────────────────────┬──────────────────────────────┘ │
│                         │                                │
│                ┌────────┴────────┐                       │
│                │  SQLite (WAL)   │                       │
│                └─────────────────┘                       │
└──────────────────────────────────────────────────────────┘
```

### 2.1 分层说明

| 层 | 目录 | 职责 |
|----|------|------|
| **Controller** | `app/controllers/` | 请求路由、参数校验、视图渲染、SSE 流式响应 |
| **Service** | `app/services/` | 核心业务逻辑（采集引擎、深度采集、定时调度） |
| **MCP** | `app/mcp/` | MCP 协议实现（Server/Client/Tools、OpenAI 格式互转） |
| **Model/Repository** | `app/models/` | 数据访问封装（Repository 模式，纯静态方法） |
| **View** | `app/templates/` | Tornado 模板渲染（Layui 后台 + 前台五区布局） |
| **Utils** | `app/utils/` | 工具函数（安全校验、审计日志、加密） |
| **Config** | `app/config/` | 全局配置 + 环境变量覆盖 |

### 2.2 数据库设计 (ER 简图)

```
users ── roles ── role_functions ── functions (树形)
  │
  ├── conversations (username 应用层关联) ── conversation_messages
  │
watch_sources ── watch_results
                   │
                   └── data_warehouse ── data_warehouse_fts (全文检索)

ai_models ── digital_employees

audit_logs (独立审计)
```

## 3. 核心模块设计

### 3.1 RBAC 权限体系

- **用户 (users)** → 关联一个角色
- **角色 (roles)** → 通过 `role_functions` 关联多个功能
- **功能 (functions)** → 两级树形结构（parent_id 自引用）
- **菜单** → 基于用户角色动态生成侧边栏菜单
- **路由级校验** → `AdminBaseHandler` 将当前请求解析为所需功能路由，按最长前缀匹配校验；`/admin/model` 可覆盖 `/admin/model/add`，但不会覆盖 `/admin/mcp/tool`
- **普通用户初始权限** → 种子数据默认给“普通用户”授予 `/admin/model/config`，满足模型 API 快速配置，其它后台能力仍需额外授权
- **登录默认落点** → 登录、注册与 `/index` 统一进入 `/chat`，后台和模型 API 配置通过前台/后台导航按权限进入

### 3.2 瞭望采集流程

```
用户输入关键词 → 选择瞭望源 (URL模板+Headers)
    → collector.py 拼装 URL → SSRF 安全校验
    → HTTP 请求采集 → HTML 解析 (baidu_news / sogou_news / generic)
    → SSE 推送 collect_progress (百分比/当前URL/成功失败数)
    → 结构化结果 → 保存到 watch_results
    → 写入 audit_logs (WATCH_COLLECT)，采集日志页可检索
    → (可选) 标记保存到 data_warehouse (URL 去重 + FTS5 索引)
    → (可选) 深度采集 (正文提取 + crawl4ai)
```

### 3.3 MCP 架构与模型引擎对话流程

```
用户消息 → POST /chat/stream
  → 有 API Key → 构建 messages + MCP tools (OpenAI Function Calling 格式)
      → LLM 返回 tool_calls 或 content
      ├─ tool_calls → MCP Server.call_tool() → 结果追加 → 继续 LLM
      └─ content → SSE 流式输出
  → 无 API Key → MCP Client 语义匹配
      → 基于工具描述多维评分 → 执行最佳匹配工具
      → 格式化结果 → SSE 流式输出
  → 写入 audit_logs (USER_CHAT)
  → Token 消耗累加到 ai_models.total_tokens
```

### 3.3b MCP 工具管理与接入流程

```
管理员进入 /admin/mcp/tool
  → 查看工具状态（启用/禁用、是否已加载）
  → 编辑内置函数路径或 HTTP API 配置
  → 在线测试：按 Input Schema 提交 JSON 参数
  → 热重载：数据库配置重新注册到 MCP Server
  → 数字员工编辑页勾选 MCP 工具权限
  → 前台 @员工 或 LLM Function Calling 按授权工具执行
```

- 内置函数工具通过 `handler_module` 动态加载 Python 处理函数。
- HTTP API 工具通过 `api_url` + `{参数名}` 占位符组装请求；GET 追加 query，POST 发送 JSON body。
- 员工未勾选任何 MCP 工具时遵循最小权限原则，不允许调用工具。

### 3.4 前台智能问数

- **A/B/C/D/E 五区布局**：LOGO(A) + 模型切换/按权限显示模型 API 配置入口(B) + 对话历史(C) + 气泡对话(D) + 输入(E)
- **SSE 流式对话**：真实 API + Mock 回退，Markdown 气泡渲染
- **多轮对话**：conversations + conversation_messages 双表持久化
- **@数字员工**：输入 `@` 触发下拉菜单，自动匹配并调用
- **ECharts 图表**：`[CHART:...]` / `[TABLE:...]` 标记自动渲染
- **模型分组隔离**：`ai_models.model_scope=admin` 表示管理员提供模型，`model_scope=user + owner_username` 表示用户自助模型；管理员页只管理 admin 组，普通用户快速配置只管理自己的 user 组
- **自助模型配置**：`/chat` 侧边栏与欢迎页快捷区按用户是否拥有 `/admin/model/config` 显示配置入口，与普通用户默认最小权限配合使用；聊天模型选择按“我的模型配置 / 管理员提供模型”分组展示
- **模型配置体验**：快速配置页遵循常见控制台交互，API Key 密码框回显、可显示/隐藏；API Base 由 Provider 白名单驱动，选择厂商后下拉展示该厂商可用接口地址，保存和 `/admin/model/config/test` 测试连接均进行后端白名单校验；连接信息变更且继续使用已保存密钥时显示醒目的确认复用区

### 3.4b 管理侧会话管理

```
管理员访问 /admin/conversation
  → ConversationRepository.get_all_admin() 跨用户分页查询
  → 可按 username / keyword 筛选
  → 点击详情读取 conversation_messages
  → 管理员删除会话时级联删除消息并写入 ADMIN_CONVERSATION_DELETE 审计日志
```

### 3.5 数字化员工

- **LLM 型**：绑定 AI 模型 + system_prompt + skills + MCP 工具权限（含 Crawl4ai 深度采集）
- **API 型**：HTTP 调用 + 参数模板 + 响应渲染模板（天气卡片等）；JSON 卡片模板会被解析为 SSE `card` 事件和自然语言摘要，避免原始 JSON 直接回显
- **默认 8 个员工**：产业专员/天机助手/天气/采集专员/文案编写/新闻聚合/科普助手/随机音乐

### 3.5.1 接口管理与 API 型员工联动（Issue #26）

```
管理员维护接口模板 (/admin/interface)
    → 填写 URL / Method / Headers / Params / Response Template / Secret
    → 表单或列表发起接口测试（SSRF + DNS 固定解析 + 禁止自动重定向 + Header CRLF 校验）
    → 创建/编辑 API 型数字员工时选择接口模板
    → 前端自动填充接口配置，服务端复用加密密钥
```

关键设计：
- 接口模板独立存储在 `api_interfaces`，多个 API 型员工可复用。
- `digital_employees.api_interface_id` 记录来源接口模板；删除接口时显式清空员工引用。
- `api_secret` 复用 Fernet 加密能力，列表 API 只返回 `has_secret`。
- `Authorization` / `Cookie` / `X-API-Key` 等敏感 Header 在联动 API 和编辑表单中脱敏展示；保存未修改的脱敏值时服务端恢复原始 Header。

### 3.6 定时采集调度

- 基于 Tornado PeriodicCallback 的轻量级调度器
- 支持按瞭望源独立配置 schedule_interval
- 专用线程池执行采集任务，不阻塞 IOLoop

### 3.7 TTS 语音合成播报（v0.9）

**设计目标**：为每条 AI 回复消息提供一键语音朗读功能，使用 Microsoft Edge TTS 免费服务。

**流程**：
```
用户点击 🔊 播报按钮
  → POST /api/chat/tts (text=AI回复内容, voice=zh-CN-XiaoxiaoNeural)
  → 后端计算 text+voice 的 MD5 作为缓存键
  → 检查 TTS 缓存目录 (~/tmp/finderos_tts/)
  ├─ 命中缓存 → 直接返回 MP3 文件
  └─ 未命中 → edge-tts.Communicate(text, voice) → 生成 MP3 → 缓存 → 返回
  → 前端收到 audio/mpeg 流 → HTML5 Audio 播放
  → 写入 audit_logs (USER_TTS)
```

**技术选型**：
| 方案 | 优点 | 缺点 | 选择 |
|------|------|------|------|
| 浏览器 Web Speech API | 零后端依赖、即时响应 | 语音质量取决于浏览器/OS，不可控 | ❌ |
| Edge TTS (Python) | 高质量神经网络语音、中文支持好、免费 | 需网络请求、首次有延迟 | ✅ |

**语音列表**（6 种中文）：
| 语音 ID | 名称 | 风格 |
|---------|------|------|
| `zh-CN-XiaoxiaoNeural` | 晓晓 | 女声，活泼 |
| `zh-CN-YunxiNeural` | 云希 | 男声，青年 |
| `zh-CN-YunjianNeural` | 云健 | 男声，中年 |
| `zh-CN-XiaoyiNeural` | 晓伊 | 女声，温柔 |
| `zh-CN-YunyangNeural` | 云扬 | 男声，新闻播报 |
| `zh-CN-XiaochenNeural` | 晓晨 | 女声，自然 |

**缓存策略**：
- 缓存目录：系统临时目录 `/finderos_tts/`
- 缓存键：`MD5(text + voice)` → `.mp3` 文件
- 不设过期时间，相同文本永久复用（文本内容不变则音频不变）
- 生成失败时自动清理损坏的缓存文件

**安全措施**：
- 文本长度限制：1-4000 字符
- 语音参数白名单校验（仅允许 6 种已知语音）
- 审计日志记录所有 TTS 调用

## 4. 安全设计

| 防护项 | 实现方式 |
|--------|---------|
| **密码存储** | PBKDF2-SHA256 (60 万轮迭代 + 16字节随机盐) |
| **CSRF** | Tornado `xsrf_cookies=True` 全局开启 |
| **XSS** | Tornado 模板默认转义 + 采集内容 HTML 清洗 |
| **SQL 注入** | 全参数化查询 (`?` 占位符) |
| **SSRF** | 校验全部 A/AAAA 地址；所有服务端外呼固定已校验 IP、禁重定向并限制响应大小 |
| **XSS** | 模板自动转义 + DOMPurify 净化 AI Markdown + 动态文本使用 DOM `textContent` |
| **后台授权** | `AdminBaseHandler` 将请求路由映射到具体功能权限，禁止跨模块访问 |
| **LLM 工具数据** | 外部工具/仓库结果作为有界不可信数据注入，建立显式信任边界并降低间接提示注入风险 |
| **Header 注入** | CRLF 字符检测 |
| **安全响应头** | CSP / X-Frame-Options / X-Content-Type-Options / X-XSS-Protection |
| **登录限速** | IP+用户名维度，5次失败/15分钟锁定 |
| **审计日志** | 关键操作全量写入 `audit_logs` 表 |
| **API Key 加密** | Fernet 对称加密存储 |
| **Prompt Injection** | System Prompt 内置安全指令约束 + `detect_prompt_injection()` / `sanitize_user_input()` 运行时检测 |

## 5. 统一接口驱动架构 (v2.0)

### 5.1 三层架构

v2.0 引入统一接口驱动架构，将所有数据访问和外部 HTTP 调用统一为三层模型：

```
数据源层 (api_interfaces) → 本地调用层 (local_api_client) → MCP 工具层 (registry)
```

| 层 | 职责 |
|----|------|
| **数据源层** | `api_interfaces` 表中注册所有数据接口，包括 18 个系统内置函数和外部 API 代理 |
| **本地调用层** | `local_api_client` 提供统一的 `call_local_api()` 入口，对内屏蔽外部 HTTP 细节；所有外网流量经 `safe_http_request`（DNS Pinning + SSRF + 审计） |
| **MCP 工具层** | `registry` 将本地接口 + 转换脚本组装为 MCP 工具，对 LLM 暴露 Function Calling 能力 |

### 5.2 tool_type 分类

MCP 工具现支持 4 种类型：

| tool_type | 说明 |
|-----------|------|
| `builtin` | 内置 Python 函数，通过 `handler_module` 动态加载 |
| `api` | HTTP API 封装，通过 `api_url` + 参数占位符组装请求 |
| `crawl4ai` | Crawl4ai 深度采集（已废弃，保留兼容） |
| `script` | **v2.0 新增**：引用 `data_sources`（本地接口） + `transform_script`（纯数据转换脚本）生成结果 |

### 5.3 script 型工具工作流程

```
LLM Function Calling → MCP Server tools/call
  → 查找工具配置 (data_sources + transform_script)
  → 遍历 data_sources，每个通过 call_local_api() 调用
      ├─ 系统内置接口 → 进程内函数直调
      └─ 外部代理接口 → safe_http_request → 外部 API
  → 收集所有 data_sources 结果 → 传入 transform_script
  → 脚本 transform(data_sources) 返回字符串
  → 字符串直接作为 MCP text content 返回给 LLM
```

脚本在 AST 白名单沙箱中执行，完全禁止 `import`、`__builtins__`、网络和文件系统访问，仅做纯数据→字符串转换。

### 5.4 架构收益

- **安全出口统一**：所有外部 HTTP 流量经 `safe_http_request`，消除分散 SSRF 风险
- **透明代理**：external 接口自动包装为虚拟 local handler，上层代码无需感知内外网
- **热重载即时生效**：接口配置和脚本均在数据库中，修改后重载即可
- **自定义 MCP 工具灵活自由**：管理员可在后台自由组合数据源 + 编写转换脚本，无需修改代码

---

## 6. 端口与配置

- 默认端口: `10010`
- 监听地址: `127.0.0.1`（可通过 `BIND_ADDRESS` 环境变量修改）
- 配置文件: `app/config/settings.py`
- 环境变量覆盖: `COOKIE_SECRET`, `DB_PATH`, `PORT`, `BIND_ADDRESS`, `DEBUG`, `PBKDF2_ITERATIONS` 等
- 数据库: `database/finderos.db` (SQLite WAL 模式)

### 6.1 系统设置（Web UI 配置中心） — #99

系统配置采用 **DB 持久化 + 内存缓存** 双层架构：

```
管理后台 /admin/config (config.html)
    │ POST 保存
    ▼
SystemConfigRepository.bulk_update()  ← 持久化到 system_config 表
    │
    ▼
settings.load_from_db()               ← 刷新内存 Settings 对象
    │ _DB_KEY_MAP 白名单映射
    ▼
Settings.XXX 属性                     ← 模板/控制器即时读取
```

**配置类别（19 项）**：

| 类别 | 数量 | 配置项 |
|------|------|--------|
| general | 5 | system_name, subtitle, logo, icp_number, default_port |
| ai | 3 | default_model, temperature, max_tokens |
| backup | 3 | db_backup_path, interval_days, keep_count |
| logging | 1 | log_level |
| notification | 2 | smtp_host, webhook_url |
| collector | 1 | collector_interval_minutes |
| security | 3 | captcha_enabled, registration_enabled, session_expire_hours |
| upload | 1 | upload_max_size_mb |

**安全设计**：
- `_DB_KEY_MAP` 白名单机制：仅允许预定义的 key 覆盖 Settings 属性
- 类型安全转换：int / float / bool 自动转换，转换失败回退默认值
- 即时生效：保存后立即调用 `load_from_db()` 刷新内存

## 7. 默认账户

| 用户名 | 密码 | 角色 |
|--------|------|------|
| admin | `ADMIN_DEFAULT_PASSWORD` 或首次启动生成的一次性随机密码 | 系统管理员 |
