# 瞭望与问数系统 (DataFinderAgentOS) — 设计文档 v0.4

## 1. 项目概述

「瞭望与问数系统」是一个轻量级的智能数据采集与 AI 问数平台，基于 Python Tornado 框架构建。
核心能力包括：
- 🔐 **用户认证与 RBAC 权限管理**
- 🔭 **瞭望采集**：可配置的 Web 数据采集引擎（百度/搜狗新闻等）
- 🗄️ **数据仓库**：采集结果的统一存储与检索
- 🤖 **模型引擎**：OpenAI 范式 AI 模型的接入管理与流式对话
- 🔗 **接口管理**：可复用 API 接口模板、接口测试、API 型数字员工联动创建

## 2. 技术架构

```
┌─────────────────────────────────────────────────┐
│                   Browser (LayUI)                │
├─────────────────────────────────────────────────┤
│                  Tornado HTTP Server             │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │
│  │ Auth     │ │ Admin    │ │ API / SSE Stream │ │
│  │ Handlers │ │ Handlers │ │ Handlers         │ │
│  └────┬─────┘ └────┬─────┘ └───────┬──────────┘ │
│       │             │              │            │
│  ┌────┴─────────────┴──────────────┴──────────┐ │
│  │           Services Layer                    │ │
│  │  ┌─────────────────┐  ┌──────────────────┐ │ │
│  │  │ collector.py    │  │ security.py      │ │ │
│  │  │ (采集+解析+SSRF) │  │ (审计+SSRF校验)   │ │ │
│  │  └─────────────────┘  └──────────────────┘ │ │
│  └────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────┐ │
│  │         Repository Layer (Models)           │ │
│  │  UserRepo / RoleRepo / FunctionRepo /      │ │
│  │  ApiInterfaceRepo / DigitalEmployeeRepo    │ │
│  └────────────────────┬───────────────────────┘ │
│                       │                         │
│              ┌────────┴────────┐                │
│              │   SQLite (WAL)  │                │
│              └─────────────────┘                │
└─────────────────────────────────────────────────┘
```

### 2.1 分层说明

| 层 | 目录 | 职责 |
|----|------|------|
| **Controller** | `app/controllers/` | 请求路由、参数校验、视图渲染 |
| **Service** | `app/services/` | 核心业务逻辑（采集、安全） |
| **Model/Repository** | `app/models/` | 数据访问封装（Repository 模式） |
| **View** | `app/templates/` | Tornado 模板渲染 |
| **Utils** | `app/utils/` | 工具函数（安全校验、审计日志） |
| **Config** | `app/config/` | 全局配置 + 环境变量覆盖 |

### 2.2 数据库设计 (ER 简图)

```
users ──┐                    watch_sources ──┐
        │ roles ── role_functions ── functions      watch_results
        └────────────────────────────────────       │
                                                 ┌──┘
ai_models    audit_logs                         │
                                            data_warehouse (via mark_saved)

api_interfaces ─────── digital_employees(API型员工联动)
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
    → (可选) 标记保存到数据仓库
```

### 3.3 模型引擎对话流程

```
用户选择模型 → 输入消息
    → 有 API Key → 真实 OpenAI API SSE 流式调用 → 返回 Token 消耗
    → 无 API Key → 本地 Mock 字符级流式输出 → 估算 Token
    → 写入 audit_logs (CHAT)
```

### 3.4 接口管理与 API 型数字员工联动

```
管理员维护接口模板 (/admin/interface)
    → 填写 URL / Method / Headers / Params / Response Template / Secret
    → 可在表单或列表中执行接口测试（SSRF + DNS 固定解析 + 禁止自动重定向 + Header CRLF 校验）
    → 创建 API 型数字员工时选择接口模板
    → 前端自动填充接口配置，服务端复用加密密钥
    → 数字员工调用时按原 API 型流程请求外部接口
```

关键设计：
- 接口模板独立存储在 `api_interfaces`，便于多个 API 型员工复用。
- `api_secret` 复用现有 Fernet 加密能力，列表 API 只返回 `has_secret`。
- `Authorization` / `Cookie` / `X-API-Key` 等敏感 Header 在联动 API 和编辑表单中脱敏展示，保存未修改的脱敏值时服务端保留原始 Header。
- `digital_employees.api_interface_id` 记录来源接口模板，便于后续追踪和编辑。
- 接口测试与 API 型员工调用不绕过安全边界：URL 需通过 `validate_url_safe()`，HTTP 客户端使用已校验 IP 连接且不自动跟随重定向，Header 需通过 CRLF 检测。

## 4. 安全设计

| 防护项 | 实现方式 |
|--------|---------|
| **密码存储** | PBKDF2-SHA256 (60 万轮迭代 + 16字节随机盐) |
| **CSRF** | Tornado `xsrf_cookies=True` 全局开启 |
| **XSS** | Tornado 模板默认转义 + 采集内容 HTML 清洗 |
| **SQL 注入** | 全参数化查询 (`?` 占位符) |
| **SSRF** | URL 协议白名单 + 内网 IP 段拦截 + DNS 解析校验 + 请求时固定已校验 IP + 禁止自动重定向 |
| **Header 注入** | CRLF 字符检测 |
| **接口密钥保护** | Fernet 加密存储，接口列表 API 不回显密钥 |
| **安全响应头** | CSP / X-Frame-Options / X-Content-Type-Options / HSTS |
| **登录限速** | IP+用户名维度，5次失败/15分钟锁定 |
| **审计日志** | 关键操作全量写入 `audit_logs` 表 |

## 5. 端口与配置

- 默认端口: `10010`
- 配置文件: `app/config/settings.py`
- 环境变量覆盖: `COOKIE_SECRET`, `DB_PATH`, `PORT`, `DEBUG`, `PBKDF2_ITERATIONS` 等
- 数据库: `database/finderos.db` (SQLite WAL 模式)

## 6. 默认账户

| 用户名 | 密码 | 角色 |
|--------|------|------|
| admin | admin888 | 系统管理员 |
