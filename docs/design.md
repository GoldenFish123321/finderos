# 瞭望与问数系统 (DataFinderAgentOS) — 设计文档 v0.4.0

## 1. 项目概述

「瞭望与问数系统」是一个轻量级的智能数据采集与 AI 问数平台，基于 Python Tornado 框架构建。
核心能力包括：
- 🔐 **用户认证与 RBAC 权限管理**
- 🔭 **瞭望采集**：可配置的 Web 数据采集引擎（百度/搜狗新闻等）
- 🗄️ **数据仓库**：采集结果的统一存储与检索（FTS5 全文检索）
- 🤖 **模型引擎**：OpenAI 范式多 Provider AI 模型的接入管理与流式对话
- 🧠 **MCP 协议**：8 个标准化工具，LLM Function Calling 智能决策调用
- 💬 **智能问数**：用户前台 A/B/C/D/E 五区 SSE 流式对话
- 🤖 **数字员工**：LLM 型 / API 型双模式，@ 触发自动匹配

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
  ├── conversations ── conversation_messages
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
    → 结构化结果 → 保存到 watch_results
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
  → 写入 audit_logs (CHAT)
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
- **默认 7 个员工**：产业专员/天机助手/天气/采集专员/文案编写/新闻聚合/科普助手

### 3.6 定时采集调度

- 基于 Tornado PeriodicCallback 的轻量级调度器
- 支持按瞭望源独立配置 schedule_interval
- 专用线程池执行采集任务，不阻塞 IOLoop

## 4. 安全设计

| 防护项 | 实现方式 |
|--------|---------|
| **密码存储** | PBKDF2-SHA256 (60 万轮迭代 + 16字节随机盐) |
| **CSRF** | Tornado `xsrf_cookies=True` 全局开启 |
| **XSS** | Tornado 模板默认转义 + 采集内容 HTML 清洗 |
| **SQL 注入** | 全参数化查询 (`?` 占位符) |
| **SSRF** | URL 协议白名单 + 内网 IP 段拦截 + DNS 解析校验 |
| **Header 注入** | CRLF 字符检测 |
| **安全响应头** | CSP / X-Frame-Options / X-Content-Type-Options / HSTS |
| **登录限速** | IP+用户名维度，5次失败/15分钟锁定 |
| **审计日志** | 关键操作全量写入 `audit_logs` 表 |
| **API Key 加密** | Fernet 对称加密存储 |
| **Prompt Injection** | 用户输入敏感词过滤 + System Prompt 安全指令 |

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
