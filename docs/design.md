# 瞭望与问数系统 (DataFinderAgentOS) — 设计文档 v0.4.2

## 1. 项目概述

「瞭望与问数系统」是一个轻量级的智能数据采集与 AI 问数平台，基于 Python Tornado 框架构建。
核心能力包括：
- 🔐 **用户认证与 RBAC 权限管理**
- 🔭 **瞭望采集**：可配置的 Web 数据采集引擎（百度/搜狗新闻等）
- 🗄️ **数据仓库**：采集结果的统一存储与检索（FTS5 全文检索）
- 🤖 **模型引擎**：OpenAI 范式多 Provider AI 模型的接入管理与流式对话
- 🧠 **MCP 协议**：数据库驱动的 18+ 工具注册中心，支持热重载和在线测试
- 💬 **智能问数**：用户前台 SSE 流式对话
- 🤖 **数字员工**：LLM 型 / API 型，支持 MCP 工具权限精细控制
- 🎯 **技能管理**：纯 Prompt 模板库，LLM 按需加载执行

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

### 3.4 前台智能问数

- **A/B/C/D/E 五区布局**：LOGO(A) + 模型切换(B) + 对话历史(C) + 气泡对话(D) + 输入(E)
- **SSE 流式对话**：真实 API + Mock 回退，Markdown 气泡渲染
- **多轮对话**：conversations + conversation_messages 双表持久化
- **@数字员工**：输入 `@` 触发下拉菜单，自动匹配并调用
- **ECharts 图表**：`[CHART:...]` / `[TABLE:...]` 标记自动渲染

### 3.5 数字化员工

- **LLM 型**：绑定 AI 模型 + system_prompt + skills + crawl4ai 可选
- **API 型**：HTTP 调用 + 参数模板 + 响应渲染模板（天气卡片等）
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

### 3.7 TTS 语音合成播报（v0.4.1）

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
| **SSRF** | URL 协议白名单 + 内网 IP 段拦截 + DNS 解析校验；接口管理/ API 员工调用固定已校验 IP 且不自动跟随重定向 |
| **Header 注入** | CRLF 字符检测 |
| **安全响应头** | CSP / X-Frame-Options / X-Content-Type-Options / X-XSS-Protection |
| **登录限速** | IP+用户名维度，5次失败/15分钟锁定 |
| **审计日志** | 关键操作全量写入 `audit_logs` 表 |
| **API Key 加密** | Fernet 对称加密存储 |
| **Prompt Injection** | System Prompt 内置安全指令约束 + `detect_prompt_injection()` / `sanitize_user_input()` 运行时检测 |

## 5. 端口与配置

- 默认端口: `10010`
- 监听地址: `127.0.0.1`（可通过 `BIND_ADDRESS` 环境变量修改）
- 配置文件: `app/config/settings.py`
- 环境变量覆盖: `COOKIE_SECRET`, `DB_PATH`, `PORT`, `BIND_ADDRESS`, `DEBUG`, `PBKDF2_ITERATIONS` 等
- 数据库: `database/finderos.db` (SQLite WAL 模式)

## 6. 默认账户

| 用户名 | 密码 | 角色 |
|--------|------|------|
| admin | admin888 | 系统管理员 |
