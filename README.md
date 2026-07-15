# 🔭 瞭望与问数系统 (DataFinderAgentOS) v0.4.2

> 基于 Tornado 异步 Web 框架构建的轻量级智能数据采集与 AI 问数一体化平台。
> **v0.4.2 完成**：MCP 重构剩余阶段全部完成 — 18 个工具种子数据迁移、三色徽章系统（蓝/绿/橙黄）、crawl4ai 废弃、Skill 绑定 MCP 工具、旧 TAG → Skill ID 迁移、测试验证通过。
> **v0.4.1 新增**：Edge TTS 语音合成播报（🔊 AI 回复一键朗读）、管理侧接口管理模块（接口模板 CRUD/测试、安全 HTTP 调用、API 型数字员工联动）。
> **v0.4.0 新增**：MCP 协议工具调用、LLM Function Calling 智能意图识别、/tools 指令。

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![Tornado](https://img.shields.io/badge/Tornado-6.4+-00ADD8?style=flat)](https://www.tornadoweb.org/)
[![SQLite](https://img.shields.io/badge/SQLite-3-003B57?style=flat&logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![Layui](https://img.shields.io/badge/Layui-2.x-1E9FFF?style=flat)](https://layui.dev/)
[![ECharts](https://img.shields.io/badge/ECharts-5.x-AA344D?style=flat)](https://echarts.apache.org/)
[![MCP](https://img.shields.io/badge/MCP-2024--11--05-6E3FF3?style=flat)](https://modelcontextprotocol.io/)
[![License](https://img.shields.io/badge/license-MIT-blue?style=flat)](LICENSE)

---

## 📋 目录

- [项目概述](#项目概述)
- [核心功能](#核心功能)
- [技术架构](#技术架构)
- [项目结构](#项目结构)
- [快速开始](#快速开始)
- [工具脚本](#工具脚本)
- [模块详解](#模块详解)
  - [1. 用户认证与安全](#1-用户认证与安全)
  - [2. RBAC 权限管理](#2-rbac-权限管理)
  - [3. 瞭望采集引擎](#3-瞭望采集引擎)
  - [4. 数据仓库](#4-数据仓库)
  - [5. AI 模型引擎](#5-ai-模型引擎)
  - [6. 菜单管理](#6-菜单管理)
  - [7. 管理后台仪表盘](#7-管理后台仪表盘)
  - [8. 数字化员工](#8-数字化员工)
  - [9. 技能管理](#9-技能管理)
  - [10. 智能问数前台](#10-智能问数前台)
  - [11. MCP 协议架构](#11-mcp-协议架构)
  - [12. TTS 语音合成播报](#12-tts-语音合成播报)
- [API 接口一览](#api-接口一览)
- [数据库设计](#数据库设计)
- [安全设计](#安全设计)
- [配置说明](#配置说明)
- [数据库迁移](#数据库迁移)
- [开发指南](#开发指南)
- [默认账户](#默认账户)
- [测试用例](#测试用例)
- [更新日志](#更新日志)
- [许可证](#许可证)

---

## 项目概述

**瞭望与问数系统 (DataFinderAgentOS)** 是一个面向中小团队的智能数据采集与 AI 问数一体化平台。它将 **Web 数据采集（瞭望）** 和 **大语言模型对话（问数）** 两大核心能力整合于统一的 Web 管理后台中，并配备完整的 RBAC 权限体系。

系统采用 **轻量依赖**设计理念：核心功能基于 Python 标准库实现（`sqlite3`、`urllib`、`hashlib`、`ssl`、`re` 等），仅引入少量必要的外部依赖（Tornado Web 框架、cryptography 加密库、Brotli 解压支持）。

### 核心能力

```
� 智能问数 — 用户前台 AI 对话         — A/B/C/D/E 五区布局 + SSE 流式 + 多轮对话
🤖 数字员工 — @ 触发智能 Agent         — 8 个默认员工 + LLM/API 双模式 + MCP 工具权限
🧰 MCP 工具 — 数据库驱动注册中心       — 18 个内置工具 + 热重载 + 在线测试 + 三色徽章
🔗 接口管理 — API 模板复用与测试       — API 型数字员工配置一键联动填充
📊 报表呈现 — ECharts 交互图表         — 柱状图/折线图/饼图/散点图 + 数据表格
🔊 语音播报 — Edge TTS 语音合成        — AI 回复一键朗读，6 种中文语音可选
�🔐 用户认证与 RBAC 权限管理          — 安全的密码存储、登录限速、审计日志
🔭 瞭望采集 — 可配置的 Web 采集引擎    — 百度/搜狗新闻等多源采集 + SSRF 防护
🗄️ 数据仓库 — 采集结果独立存储与检索   — 独立 data_warehouse 表，支持去重
🤖 模型引擎 — 多 Provider AI 统一管理  — OpenAI/DeepSeek/智谱/文心 + MCP 工具调用
📊 管理后台 — Layui 精美 UI，开箱即用  — 仪表盘统计、树形菜单、批量操作
🛡️ 安全防护 — OWASP Top 10 全覆盖     — CSP/XSRF/SSRF/SQL注入/XSS/限速/审计
```

### 适用场景

- 新闻舆情监控与自动采集
- 企业内部知识库的数据沉淀
- 多模型 AI 对话的统一管理入口
- 轻量级 RBAC 后台管理系统的快速搭建
- 学习 Tornado 全栈开发的教学参考项目

---

## 技术架构

### 整体分层

```
┌─────────────────────────────────────────────────────────┐
│                    Browser (Layui 2.x)                   │
├─────────────────────────────────────────────────────────┤
│                 Tornado HTTP Server                      │
│  ┌────────────┐ ┌────────────┐ ┌──────────────────────┐ │
│  │ Auth       │ │ Admin      │ │ API / SSE Stream     │ │
│  │ Handlers   │ │ Handlers   │ │ Handlers             │ │
│  └─────┬──────┘ └─────┬──────┘ └────────┬─────────────┘ │
│        │              │                │                │
│  ┌─────┴──────────────┴────────────────┴─────────────┐  │
│  │              Services Layer                        │  │
│  │  ┌────────────────────┐  ┌──────────────────────┐ │  │
│  │  │ collector.py       │  │ security.py          │ │  │
│  │  │ 采集引擎+HTML解析   │  │ SSRF校验+审计日志     │ │  │
│  │  │ +SSRF防护+反爬      │  │ +CRLF检测            │ │  │
│  │  └────────────────────┘  └──────────────────────┘ │  │
│  │  ┌────────────────────────────────────────────┐   │  │
│  │  │          MCP Layer (app/mcp/)               │   │  │
│  │  │  Server · Client · Tools · OpenAI 格式适配  │   │  │
│  │  └────────────────────────────────────────────┘   │  │
│  └───────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────┐  │
│  │           Repository Layer (Models)                │  │
│  │  UserRepo / RoleRepo / FunctionRepo /             │  │
│  │  WatchSourceRepo / WatchResultRepo /              │  │
│  │  DataWarehouseRepo / AiModelRepo                  │  │
│  └──────────────────────┬────────────────────────────┘  │
│                         │                               │
│                ┌────────┴────────┐                      │
│                │  SQLite (WAL)   │ 16 张表 + FTS5     │
│                └─────────────────┘                      │
└─────────────────────────────────────────────────────────┘
```

### 分层职责

| 层 | 目录 | 职责 |
|----|------|------|
| **Controller** | `app/controllers/` | 请求路由、参数校验、视图渲染、SSE 流式响应 |
| **Service** | `app/services/` | 核心业务逻辑（数据采集、HTML 解析、SSRF 防护、反爬策略） |
| **Model/Repository** | `app/models/` | 数据访问封装，统一使用 Repository 模式（纯静态方法） |
| **View** | `app/templates/` | Tornado 原生模板 + Layui 2.x 前端组件 |
| **Utils** | `app/utils/` | 工具函数（密码学、SSRF 校验、CRLF 检测、审计日志） |
| **Config** | `app/config/` | 全局配置中心，所有配置支持环境变量覆盖 |

### 技术栈

| 类别 | 技术 | 说明 |
|------|------|------|
| **语言** | Python 3.11+ | 类型注解、现代语法 |
| **Web 框架** | Tornado 6.4+ | 异步非阻塞 HTTP 服务器 |
| **数据库** | SQLite 3 (WAL 模式) | 零配置、嵌入式、单文件，支持并发读 |
| **前端框架** | Layui 2.x | 经典模块化 UI 框架 |
| **前端其他** | 原生 HTML / CSS / JS | 无构建工具依赖，零前端编译 |
| **密码学** | PBKDF2-SHA256 | 60 万轮迭代 + 16 字节随机盐（hex 存储） |
| **数据采集** | Python 标准库 `urllib` | 零第三方爬虫依赖 |
| **HTML 解析** | Python `re` 正则 | 内置解析器，无需 BeautifulSoup |
| **AI 对话** | OpenAI 范式 SSE + Function Calling | 支持 OpenAI / DeepSeek / 智谱 AI / 百度文心 / 自定义 Provider |
| **工具协议** | MCP (Model Context Protocol) | 18 个标准化工具，数据库驱动注册中心 + 热重载 + 在线测试 |

---

## 项目结构

```
DataFinderAgentOS/
├── main.py                       # 程序主入口（路由注册 + Tornado 启动）
├── make_admin.py                 # 管理员账号创建/重置工具（命令行）
├── migrate_db.py                 # 数据库迁移脚本（向后兼容）
├── requirements.txt              # Python 依赖清单（tornado + cryptography + brotli）
├── README.md                     # 项目文档（本文件）
│
├── database/                     # SQLite 数据库文件目录
│   └── finderos.db               # 主数据库文件（首次启动自动生成）
│
├── docs/                         # 项目文档
│   ├── design.md                 # 系统设计文档
│   ├── requirement.md            # 需求文档
│   ├── api.md                    # API 接口文档
│   ├── constraint.md             # 全局开发约束（DDL、安全规范等）
│   ├── test_case.md              # 测试用例清单（58 项）
│   └── v0.3_gap_analysis_and_plan.md  # v0.3 差距分析与规划（已归档）
│
├── test/                         # 单元测试与 Bug 回归测试
│   ├── __init__.py
│   ├── _smoke_encryption.py      # 加密模块冒烟测试
│   ├── test_login_rate_limiter.py
│   ├── test_user_models.py
│   ├── test_v0_3_enhancements.py
│   ├── test_bugs_1_2_3.py
│   ├── test_bug3_role_delete_500.py
│   ├── test_bug4_cookie_race.py
│   ├── test_bug4_hardcoded_role_name.py
│   ├── test_bug5_child_rf_cleanup.py
│   ├── test_bug5_threadpool.py
│   ├── test_bug6_api_key_clear.py
│   ├── test_bug6_rate_limiter_cleanup.py
│   ├── test_bug7_dw_dedup.py
│   ├── test_bug7_watch_url_dedup.py
│   ├── test_bug8_batch_admin_feedback.py
│   ├── test_bug8_self_operation.py
│   ├── test_bug9_watchsave_format.py
│   ├── test_bug9_watchsave_msg.py
│   ├── test_bug10_admin_audit_log.py
│   ├── test_bug11_index_template.py
│   ├── test_bug12_rowcount.py
│   ├── test_bugs_14_15_16.py
│   ├── test_bug17_batch_delete_rowcount.py
│   ├── test_bug27_jquery_array_save.py
│   ├── test_bug28_warehouse_detail_columns.py
│   └── test_bug30_chat_default_model.py
│
├── app/
│   ├── config/                   # 配置模块
│   │   ├── __init__.py
│   │   └── settings.py           # 全局配置（环境变量覆盖）
│   │
│   ├── controllers/              # 控制器层（Handler）
│   │   ├── __init__.py
│   │   ├── auth.py               # 登录/登出/注册 + 频率限制器
│   │   ├── base.py               # 公共基础 Handler（认证 + 安全响应头）
│   │   ├── home.py               # 前台主页控制器 → 跳转 /chat
│   │   ├── user_chat.py          # 用户前台智能问数（A/B/C/D/E 五区 + SSE + @员工 + 图表）
│   │   ├── admin_base.py         # 管理后台基础 Handler（权限校验）
│   │   ├── admin_home.py         # 管理后台仪表盘（统计卡片）
│   │   ├── admin_user.py         # 用户管理 CRUD + 批量操作
│   │   ├── admin_role.py         # 角色管理 CRUD + 功能权限树联动
│   │   ├── admin_function.py     # 功能管理 CRUD（树形结构 + 启用/禁用）
│   │   ├── admin_menu.py         # 菜单管理（角色→菜单预览 + 排序）
│   │   ├── admin_watch.py        # 瞭望采集页 + SSE 进度推送 + 保存仓库 + 深度采集
│   │   ├── admin_watch_source.py # 瞭望源管理 CRUD + 启用/禁用
│   │   ├── admin_warehouse.py    # 数据仓库列表/详情/单删/批量删除 + 深度采集
│   │   ├── admin_model.py        # 模型引擎 CRUD（对话已统一迁移至前台 /chat）
│   │   ├── admin_conversation.py # 管理侧会话管理（跨用户查看/详情/删除）
│   │   ├── admin_employee.py     # 数字化员工 CRUD + SSE 调用 + 测试页
│   │   ├── admin_skill.py        # 技能管理 CRUD + MCP 工具绑定（v0.5.0）
│   │   ├── admin_mcp.py          # MCP 工具管理 CRUD + 测试 + 热重载（v0.4.2）
│   │   └── admin_interface.py    # 接口管理 CRUD + 测试（v0.4.1）
│   │
│   ├── models/                   # 数据模型层（Repository 模式）
│   │   ├── __init__.py
│   │   ├── db.py                 # 数据库连接池 + 建表 + 种子数据
│   │   ├── user.py               # UserRepository — 用户仓储
│   │   ├── role.py               # RoleRepository — 角色仓储
│   │   ├── function.py           # FunctionRepository — 功能仓储
│   │   ├── watch_source.py       # WatchSourceRepository — 瞭望源仓储
│   │   ├── watch_result.py       # WatchResultRepository — 采集结果仓储
│   │   ├── data_warehouse.py     # DataWarehouseRepository — 数据仓库仓储
│   │   ├── ai_model.py           # AiModelRepository — AI 模型仓储
│   │   ├── conversation.py       # ConversationRepository — 对话管理仓储（v0.3）
│   │   ├── digital_employee.py   # DigitalEmployeeRepository — 数字员工仓储（v0.3）
│   │   ├── skill.py              # SkillRepository — 技能仓储（v0.5.0）
│   │   ├── mcp_tool.py           # MCPToolRepository — MCP 工具仓储（v0.4.2）
│   │   └── api_interface.py      # ApiInterfaceRepository — 接口模板仓储（v0.4.1）
│   │
│   ├── mcp/                      # MCP 协议模块（v0.4）
│   │   ├── __init__.py           # 模块入口
│   │   ├── server.py             # MCP Server（工具注册、MCP/OpenAI 格式互转）
│   │   ├── client.py             # MCP Client（工具执行、智能语义匹配、上下文注入）
│   │   ├── tools.py              # 18 个 MCP 工具定义 + 处理函数（代码回退）
│   │   ├── registry.py           # 数据库驱动工具注册中心（v0.4.2）
│   │   └── builtin_tools/        # 按分类组织的工具处理函数（8 个模块）
│   │       ├── warehouse_tools.py
│   │       ├── collect_tools.py
│   │       ├── employee_tools.py
│   │       ├── model_tools.py
│   │       ├── chat_tools.py
│   │       ├── entertainment_tools.py
│   │       ├── crawl4ai_tools.py
│   │       └── system_tools.py
│   │
│   ├── services/                 # 业务服务层
│   │   ├── __init__.py
│   │   ├── collector.py          # 采集引擎（HTTP 请求 + HTML 解析 + SSRF + 反爬）
│   │   ├── deep_collector.py     # 深度采集引擎（正文提取 + crawl4ai）（v0.3）
│   │   └── scheduler.py          # 定时采集调度器（v0.3）
│   │
│   ├── utils/                    # 工具模块
│   │   ├── __init__.py
│   │   └── security.py           # SSRF 校验 + 审计日志 + CRLF 检测 + API Key 加密
│   │
│   ├── templates/                # Tornado 模板
│   │   ├── base.html             # 基础布局模板
│   │   ├── login.html            # 登录页
│   │   ├── register.html         # 注册页
│   │   ├── user_index.html       # 前台首页（统计卡片，自动跳转 /chat）
│   │   ├── user_chat.html        # 前台智能问数主页（A/B/C/D/E 五区布局）（v0.3）
│   │   └── admin/                # 管理后台模板
│   │       ├── base_layout.html       # 后台布局（侧边栏 + 顶栏）
│   │       ├── index.html             # 仪表盘首页
│   │       ├── user_list.html         # 用户列表
│   │       ├── user_form.html         # 用户新增/编辑表单
│   │       ├── role_list.html         # 角色列表
│   │       ├── role_form.html         # 角色表单（含功能权限树）
│   │       ├── function_list.html     # 功能列表（树形展示）
│   │       ├── function_form.html     # 功能表单
│   │       ├── menu.html              # 菜单预览（按角色）
│   │       ├── watch.html             # 瞭望采集页（进度条 + EventSource）
│   │       ├── watch_log.html         # 采集日志页
│   │       ├── watch_source_list.html # 瞭望源列表
│   │       ├── watch_source_form.html # 瞭望源表单
│   │       ├── warehouse.html         # 数据仓库列表
│   │       ├── warehouse_detail.html  # 采集结果详情
│   │       ├── model_list.html        # 模型引擎列表
│   │       ├── model_form.html        # 模型表单
│   │       ├── conversation_list.html # 管理侧会话列表/详情
│   │       ├── employee_list.html     # 数字员工列表（v0.3）
│   │       ├── employee_form.html     # 数字员工表单（v0.3）
│   │       ├── employee_test.html     # 数字员工测试页（v0.3）
│   │       ├── skill_list.html        # 技能列表（v0.5.0）
│   │       ├── skill_form.html        # 技能表单（v0.5.0）
│   │       ├── mcp_tool_list.html     # MCP 工具列表（v0.4.2）
│   │       ├── mcp_tool_form.html     # MCP 工具表单（v0.4.2）
│   │       └── change_password.html   # 修改密码
│   │
│   └── static/                   # 静态资源
│       ├── css/
│       │   ├── base.css          # 全局样式
│       │   ├── dark-theme.css    # 暗色主题样式
│       │   └── light-theme.css   # 浅色主题样式
│       └── js/
│           └── base.js           # 全局脚本
```

---

## 快速开始

### 环境要求

| 项目 | 最低版本 | 推荐版本 |
|------|---------|---------|
| **Python** | 3.11 | 3.13+ |
| **操作系统** | Windows / macOS / Linux | — |
| **磁盘空间** | ~50 MB（含虚拟环境和数据库） | — |
| **内存** | 128 MB | 512 MB+ |

### 安装与运行

#### 1. 进入项目目录

```bash
cd day7-1
```

#### 2. 创建虚拟环境

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
```

#### 3. 安装依赖

```bash
pip install -r requirements.txt
```

> **核心外部依赖**：`tornado>=6.4`（Web 框架）、`cryptography>=41.0`（API Key 加密）、`brotli>=1.1`（HTTP 解压）、`crawl4ai>=0.4`（深度采集，可选）。
> 数据库、HTTP 采集、HTML 基础解析、密码哈希等功能均使用 Python 标准库。

#### 4. 启动服务

```bash
python main.py
```

启动成功后终端输出：

```
==================================================
  瞭望与问数系统 (DataFinderAgentOS) v0.4.2
  Server started: http://localhost:10010/
==================================================
```

> 首次启动时系统会自动：
> 1. 创建 `database/` 目录和 `finderos.db` 数据库文件
> 2. 执行 `CREATE TABLE IF NOT EXISTS` 建表（16 张表 + 1 张 FTS5 虚拟表）
> 3. 创建数据库索引（10+ 个索引）
> 4. 插入种子数据（默认角色、管理员账户、功能菜单）

#### 5. 访问系统

打开浏览器，访问 **http://localhost:10010/**，使用默认账户登录：

| 用户名 | 密码 | 角色 | 跳转页面 |
|--------|------|------|----------|
| `admin` | `admin888` | 系统管理员 | `/admin` 管理后台 |

> ⚠️ **首次登录后请立即修改默认密码！**

#### 6. 停止服务

在终端按 `Ctrl + C` 即可停止服务。

### 自定义端口

```bash
# Windows PowerShell
$env:PORT = "8080"; python main.py

# Linux / macOS
PORT=8080 python main.py
```

---

## 工具脚本

项目提供了两个独立的命令行工具，无需启动 Web 服务即可使用。

### `make_admin.py` — 管理员账号管理

用于快速创建、重置或查看管理员账号。

```bash
# 交互式创建管理员
python make_admin.py

# 命令行指定用户名和密码
python make_admin.py --username admin --password admin888

# 指定角色 ID（1=系统管理员, 2=普通用户）
python make_admin.py --username admin --password admin888 --role-id 1

# 列出所有用户
python make_admin.py --list

# 重置已有用户的密码
python make_admin.py --reset --username admin --password newpass
```

### `migrate_db.py` — 数据库迁移

向后兼容地为现有数据库添加新列/新表，不破坏已有数据。

```bash
# 执行所有待处理的迁移
python migrate_db.py

# 查看迁移状态
python migrate_db.py --status
```

迁移历史：

| 版本 | 变更内容 |
|------|---------|
| v0.2.5 | 添加 `ai_models.total_tokens`（Token 累加统计） |
| v0.2.5 | 添加 `audit_logs` 表（操作审计日志） |
| v0.2.5 | 添加安全相关索引 |
| v0.2.13 | 添加 `data_warehouse` 独立表 + URL 去重索引 |
| v0.3.0 | 添加 `conversations` / `conversation_messages` 表 |
| v0.3.0 | 添加 `digital_employees` 表 |
| v0.3.0 | 添加 `data_warehouse_fts` FTS5 虚拟表 + 同步触发器 |
| v0.4.0 | 添加 `watch_sources.schedule_interval` 列 |
| v0.4.1 | 添加 `api_interfaces` 表与 `digital_employees.api_interface_id`（接口管理联动） |
| v0.4.2 | 添加 `mcp_tools` / `mcp_tool_test_logs` 表（MCP 工具数据库驱动注册中心） |
| v0.4.2 | 添加 `skills.mcp_tool_id` 列 + `digital_employees.mcp_tool_ids` 列 |
| v0.4.2 | 种子数据迁移：18 个内置 MCP 工具 + 旧 TAG → Skill ID 迁移 |

> 迁移脚本具有**幂等性**：重复执行不会破坏已有数据。

---

## 模块详解

### 1. 用户认证与安全

#### 1.1 登录流程

```
用户输入凭证
    → 频率限制检查（IP + 用户名维度，5 次/15 分钟）
    → PBKDF2-SHA256 密码验证（60 万轮迭代）
    → 检查 is_enabled 状态
    → 成功: set_secure_cookie + 按功能权限跳转
        ├── 有后台功能权限 → /admin（管理后台仪表盘）
        └── 无后台功能权限 → /index（前台主页）
    → 失败: 记录失败次数 + 返回错误提示
    → 锁定: 超过阈值后返回"账户已锁定"提示
```

#### 1.2 安全特性汇总

| 特性 | 实现方式 | 参考标准 |
|------|---------|---------|
| **密码存储** | PBKDF2-SHA256，60 万轮迭代，16 字节随机盐（hex 存储） | OWASP 2023 |
| **会话管理** | Tornado Secure Cookie（`set_secure_cookie` / `get_secure_cookie`） | — |
| **CSRF 防护** | 全局 `xsrf_cookies=True`，模板中 `{% module xsrf_form_html() %}` | OWASP A01:2021 |
| **登录限速** | IP + 用户名维度，5 次失败 / 15 分钟锁定窗口 | OWASP A07:2021 |
| **安全响应头** | CSP、X-Frame-Options、X-Content-Type-Options、X-XSS-Protection、Referrer-Policy、Permissions-Policy | OWASP |
| **审计日志** | 登录/登出/锁定等关键操作写入 `audit_logs` 表 | OWASP A09:2021 |
| **XSS 防护** | Tornado 模板默认 HTML 转义 + 采集内容清洗 | OWASP A03:2021 |
| **SQL 注入防护** | 全参数化查询（`?` 占位符），杜绝字符串拼接 | OWASP A03:2021 |
| **Header 注入防护** | CR/LF 字符检测（`has_crlf()`） | OWASP A03:2021 |

#### 1.3 认证拦截链

```
未登录请求
    → BaseHandler.get_current_user() 返回 None
    → @tornado.web.authenticated 装饰器拦截
    → 302 重定向到 login_url="/"（登录页）

已登录但角色无权限
    → AdminBaseHandler.prepare() 校验
    → 角色为"普通用户" → 403 权限不足页面
    → 用户被禁用 → 清除 Cookie + 302 重定向

已登录且角色有权限
    → 正常进入管理后台页面
```

#### 1.4 登录频率限制器

`LoginRateLimiter` 类位于 `app/controllers/auth.py`，支持独立作用域：

```python
# 创建限速器（支持不同作用域隔离计数）
limiter = LoginRateLimiter(scope="admin")
# 检查是否允许尝试
allowed, msg = limiter.check(client_ip, username)
# 记录失败
limiter.record_failure(client_ip, username)
# 成功后清除
limiter.clear(client_ip, username)
```

---

### 2. RBAC 权限管理

#### 2.1 权限模型

```
用户 (users)  ──1:1──▶  角色 (roles)  ──M:N──▶  功能 (functions)
                                                    │
                                              parent_id 自引用
                                              （支持两级树形结构）
```

- **用户 ↔ 角色**：每个用户绑定一个角色（`users.role_id`）
- **角色 ↔ 功能**：通过 `role_functions` 中间表实现多对多关联
- **功能**：支持两级树形（`parent_id` 自引用），每项功能可配置图标、路由、排序
- **菜单生成**：角色 → `role_functions` → `functions` → 按 `parent_id` 构建树 → 过滤 `is_enabled=1` → 按 `sort_order` 排序

#### 2.2 用户管理 (`/admin/user`)

| 功能 | 说明 |
|------|------|
| 列表查看 | 分页（20 条/页）、关键词搜索、三区布局（搜索+表格+分页） |
| 新增用户 | 用户名 + 密码 + 角色选择 |
| 编辑用户 | 修改密码（留空不修改）、更换角色 |
| 启用/禁用 | 单个切换 + 批量切换 |
| 删除用户 | 单个删除 + 批量删除 |
| 安全保护 | `admin` 用户不可删除、不可禁用自身 |

#### 2.3 角色管理 (`/admin/role`)

| 功能 | 说明 |
|------|------|
| 新增角色 | 角色名 + 描述 + 功能权限树勾选 |
| 编辑角色 | 修改角色信息 + 更新功能权限关联 |
| 删除角色 | 删除角色（自动清理 `role_functions` 关联） |
| 系统角色保护 | `is_system=1` 的角色（系统管理员、普通用户）不可编辑/删除 |
| 功能权限联动 | Layui 树形组件（`tree`）展示全部功能，勾选即授权，自动同步 `role_functions` 中间表 |

#### 2.4 功能管理 (`/admin/function`)

| 功能 | 说明 |
|------|------|
| 树形展示 | 一级功能 + 二级子功能，Layui 树形表格 |
| 新增功能 | 功能名 + 图标 + 路由 + 父级选择 + 排序 |
| 编辑功能 | 修改功能属性 |
| 启用/禁用 | 切换 + 禁用级联（禁用后自动清除所有角色对该功能的关联） |
| 删除功能 | 删除功能节点（含子节点处理） |

#### 2.5 默认权限体系

| 角色 | 后台访问 | 说明 |
|------|---------|------|
| 系统管理员 (id=1) | ✅ 全部功能 | 拥有所有后台功能的访问权限，不可删除/编辑 |
| 普通用户 (id=2) | ❌ 仅前台 | 只能访问登录后的前台主页 `/index`，不可删除/编辑 |
| 自定义角色 | 取决于配置 | 通过角色管理分配具体功能权限 |

---

### 3. 瞭望采集引擎

#### 3.1 概述

瞭望采集引擎是系统的核心数据入口，支持配置多个「瞭望源」（Watch Source），通过 **URL 模板 + 关键词 + 自定义 HTTP Headers** 的方式自动抓取并解析 Web 数据。

#### 3.2 采集流程

```
用户输入关键词
    → 选择瞭望源（URL 模板 + 自定义 Headers）
    → collector.py 拼装 URL
        ├── {keyword} → URL 编码后的关键词
        ├── {page}    → 当前页码
        └── 支持复杂表达式：{(page-1)*10}
    → SSRF 安全校验
        ├── 协议白名单: 仅 http / https
        ├── CRLF 检测: 拒绝含 \r \n 的 URL
        ├── DNS 解析: hostname → IP
        └── IP 黑名单: 回环地址 + 内网地址段
    → 发起 HTTP GET 请求
        ├── 模拟 Chrome 138 TLS 指纹
        ├── 全局 CookieJar 维持会话
        └── 自定义 Request Headers
    → 响应解压（gzip / deflate）
    → 按 parser 类型解析 HTML
    → SSE 推送 collect_progress（百分比、当前 URL、成功/失败数）
    → 结构化结果返回（collect_done / JSON）
    → 保存到 watch_results 表
    → （可选）标记保存到 data_warehouse 独立表
    → 写入 audit_logs（WATCH_COLLECT），供采集日志页检索
```

#### 3.3 内置解析器

| 解析器 | 函数名 | 标识 | 适用场景 | 解析能力 |
|--------|--------|------|---------|---------|
| 百度新闻解析 | `parse_baidu_news` | `baidu_news` | 百度新闻搜索结果 | 标题、链接、摘要、来源 |
| 搜狗新闻解析 | `parse_sogou_news` | `sogou_news` | 搜狗新闻搜索结果 | 标题、链接、摘要 |
| 通用解析 | `generic_parse` | `generic` | 通用网页 | 提取 h2/h3 标签中的链接 |

#### 3.4 瞭望源管理 (`/admin/watch/source`)

瞭望源是可复用的数据采集配置，核心字段：

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `name` | TEXT | 瞭源名称 | 百度新闻 |
| `description` | TEXT | 瞭源描述 | 百度新闻搜索结果采集 |
| `url_template` | TEXT | URL 模板（支持占位符） | `https://www.baidu.com/s?tn=news&word={keyword}&pn={(page-1)*10}` |
| `request_headers` | TEXT(JSON) | 自定义 HTTP 请求头 | `{"Referer":"https://www.baidu.com/"}` |
| `sort_order` | INTEGER | 排序权重 | 数字越小越靠前 |
| `schedule_interval` | INTEGER | 定时采集间隔（分钟） | 0=不启用，60=每小时 |
| `is_enabled` | INTEGER | 启用状态 | 1=启用, 0=禁用 |

支持的操作：**新增、编辑、删除、启用/禁用切换**。

#### 3.5 采集进度与日志 (`/admin/watch/stream`, `/admin/watch/log`)

- 采集页优先使用 `EventSource` 连接 `/admin/watch/stream`，后端按瞭望源逐个推送 `collect_progress` 事件。
- `collect_progress` 数据包含 `percent`、`current_url`、`success`、`failed`、`message`，前端渲染为实时进度条。
- 采集完成后发送 `collect_done`，携带新闻列表、成功/失败计数；异常时发送 `collect_error`。
- 采集动作写入 `audit_logs`，采集日志页按 `COLLECT` 类动作筛选展示，支持关键词搜索和分页。

#### 3.6 百度反爬策略

- 首次访问百度时会自动预热 Cookie（先请求首页获取 `BAIDUID` 等关键 Cookie）
- 使用全局 `CookieJar` 维持会话状态，避免每次请求都触发验证码
- 模拟 Chrome 138 浏览器的 TLS 指纹和 User-Agent
- 自定义 HTTP Headers（Referer、Accept-Language 等）
- 建议请求间隔 ≥ 3 秒以避免触发频率限制

#### 3.7 URL 模板占位符

| 占位符 | 说明 | 示例 |
|--------|------|------|
| `{keyword}` | URL 编码后的搜索关键词 | `人工智能` → `%E4%BA%BA%E5%B7%A5%E6%99%BA%E8%83%BD` |
| `{page}` | 当前页码 | `1`, `2`, `3`... |
| `{(page-1)*10}` | 计算表达式（用于百度 `pn` 参数） | 第1页→0, 第2页→10, 第3页→20... |

---

### 4. 数据仓库

#### 4.1 概述

数据仓库 (`/admin/warehouse`) 是瞭望采集结果的**独立存储与检索中心**。v0.2.13 起采用独立的 `data_warehouse` 表（区别于原始采集结果表 `watch_results`），支持 URL 去重和深度采集扩展。

#### 4.2 两表设计

| 表 | 用途 | 特点 |
|----|------|------|
| `watch_results` | 原始采集结果 | 每次采集都保存，含 HTTP 状态码、响应大小等元信息 |
| `data_warehouse` | 独立数据仓库 | 从采集结果中"标记保存"而来，含标题/链接/摘要/来源等结构化字段，支持 URL 去重 |

#### 4.3 主要功能

| 功能 | 说明 |
|------|------|
| **列表浏览** | 分页展示所有仓库数据（20 条/页），含标题、来源、采集时间 |
| **关键词搜索** | 按标题或来源名称模糊检索 |
| **统计概览** | 显示总采集条数、成功/失败统计 |
| **详情查看** | 点击查看单条记录的完整信息（标题、链接、摘要、原始数据等） |
| **批量删除** | 勾选多条后一键删除 |
| **数据保存** | 从瞭望采集页可将结果标记"保存到仓库"，自动写入 `data_warehouse` 表 |
| **URL 去重** | `link` 字段设唯一索引，重复 URL 自动跳过 |

#### 4.4 数据仓库表结构

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 自增主键 |
| `result_id` | INTEGER FK | 关联原始采集结果 |
| `title` | TEXT | 新闻标题 |
| `link` | TEXT (UNIQUE) | 新闻链接（唯一索引去重） |
| `summary` | TEXT | 摘要内容 |
| `source_name` | TEXT | 来源名称 |
| `raw_data` | TEXT | 原始数据（JSON） |
| `is_deep_collected` | INTEGER | 是否已深度采集（预留字段） |
| `deep_collected_at` | TIMESTAMP | 深度采集时间（预留字段） |
| `created_at` | TIMESTAMP | 入库时间 |

---

### 5. AI 模型引擎（MCP 架构版）

#### 5.1 概述

模型引擎提供**多 Provider AI 大模型**的统一管理平台，v0.4 升级为 **MCP（Model Context Protocol）架构**：

- **有 API Key**：LLM Function Calling 自主决策工具调用，Tool → Execute → Reply 闭环
- **无 API Key**：MCP 语义匹配智能回退，基于工具描述自动路由到最佳工具
- **工具标准化**：18 个 MCP Tool，数据库驱动注册中心（`mcp_tools` 表），支持热重载和在线测试
- **OpenAI 兼容**：工具定义自动转换为 OpenAI Function Calling 格式，无缝对接主流 LLM

**MCP 工具分类（18 个）**：

| 分类 | 工具 | 说明 |
|------|------|------|
| 🔍 数据仓库 | `search_warehouse`, `get_recent_warehouse_data`, `get_warehouse_stats`, `search_warehouse_fulltext` | 关键词搜索、最新数据、统计、FTS5 全文检索 |
| 🔭 瞭望采集 | `collect_web_data`, `deep_collect_url`, `list_watch_sources` | 全网采集、深度采集 URL、瞭望源列表 |
| 🤖 数字员工 | `list_digital_employees`, `invoke_digital_employee` | 员工列表、调用指定员工 |
| 🧠 AI 模型 | `list_ai_models`, `get_default_model` | 模型列表、获取默认模型 |
| 💬 对话管理 | `list_conversations`, `get_conversation_messages` | 对话历史、消息查询 |
| 🎵 娱乐 | `get_random_music` | 随机音乐推荐 |
| 🕷️ 爬虫增强 | `collect_with_crawl4ai`, `batch_deep_collect` | Crawl4ai 智能/批量采集 |
| 🔧 系统 | `load_skill`, `get_system_stats` | 技能加载、系统统计 |

**对话流程（有 API Key）**：

```
用户消息 → POST /chat/stream
  → 构建 messages + MCP tools (OpenAI 格式)
  → LLM 返回 tool_calls 或 content
  ├─ tool_calls → MCP Server.call_tool() → 结果追加到 messages → 继续 LLM 对话
  └─ content → SSE 流式输出最终回复
```

**对话流程（无 API Key - MCP 回退）**：

```
用户消息 → MCP Client.match_tool_by_query()
  → 基于工具描述语义评分匹配最佳工具
  → 执行工具 → _format_tool_result_as_reply() → SSE 流式输出
  → 无匹配 → 通用 Mock 回复
```

支持的 Provider：

| Provider | 标识 | API 范式 |
|----------|------|---------|
| OpenAI | `openai` | OpenAI Chat Completions |
| DeepSeek | `deepseek` | OpenAI 兼容 |
| 智谱 AI | `zhipu` | OpenAI 兼容 |
| 百度文心 | `baidu` | OpenAI 兼容 |
| 自定义 | `custom` | OpenAI 兼容（任意兼容端点） |

支持的模型分类（6 种）：

| 分类 | 标识 | 说明 |
|------|------|------|
| 文本 | `text` | 纯文本对话模型（如 GPT-4o、DeepSeek-V3） |
| 图像 | `image` | 图像生成模型（如 DALL·E） |
| 音频 | `audio` | 音频处理模型（如 Whisper） |
| 视频 | `video` | 视频处理模型（如 Sora） |
| 多模态 | `multimodal` | 多模态理解模型（如 GPT-4V） |
| 嵌入 | `embedding` | 文本嵌入模型（如 text-embedding-3） |

#### 5.2 模型管理 (`/admin/model`)

每个模型支持完整的参数配置：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `name` | TEXT | — | 模型显示名称（如"GPT-4o"） |
| `provider` | TEXT | `openai` | 提供商标识 |
| `api_base` | TEXT | — | API 端点 URL（如 `https://api.openai.com/v1`） |
| `api_key` | TEXT | — | API 密钥 |
| `model_name` | TEXT | — | 模型标识（如 `gpt-4o`、`deepseek-chat`） |
| `category` | TEXT | `text` | 模型分类 |
| `system_prompt` | TEXT | — | 系统提示词 |
| `temperature` | REAL | `0.7` | 温度参数（0~2） |
| `top_p` | REAL | `1.0` | Top-P 采样 |
| `top_k` | INTEGER | `50` | Top-K 采样 |
| `max_tokens` | INTEGER | `4096` | 最大输出 Token |
| `context_size` | INTEGER | `8192` | 上下文窗口大小 |
| `total_tokens` | INTEGER | `0` | Token 消耗累计（自动更新） |
| `is_enabled` | INTEGER | `1` | 启用状态 |
| `is_default` | INTEGER | `0` | 是否默认模型（全局唯一） |

支持的操作：**新增、编辑、删除、启用/禁用、设为默认**。

> **注**：模型流式对话功能已统一迁移至前台 `/chat/stream`（MCP 架构），后台不再提供独立对话页面。

#### 5.3 模型 API 接口

| 端点 | 说明 |
|------|------|
| `GET /admin/api/model/list` | 返回已启用模型的 JSON 列表（供外部调用） |

---

### 6. 菜单管理

#### 6.1 概述

菜单管理 (`/admin/menu`) 提供按角色**预览后台侧边栏菜单树**的功能，并支持菜单项排序。

#### 6.2 菜单生成逻辑

```
角色 → RoleRepository.get_function_ids(role_id)
    → FunctionRepository.get_all() 获取全部功能
    → 过滤: function_id 在角色权限内 且 is_enabled=1
    → 按 parent_id 构建树形结构
    → 按 sort_order 排序
    → 渲染为 Layui 侧边栏菜单
    → 同时以 JSON 格式展示原始结构（便于调试）
```

#### 6.3 菜单排序 (`/admin/menu/sort`)

支持菜单项的上移/下移操作（修改 `functions.sort_order`），实现侧边栏菜单的自定义排序。

---

### 7. 管理后台仪表盘

管理后台首页 (`/admin`) 提供系统全局统计概览，以 Layui 卡片形式展示：

| 统计项 | 数据来源 | 说明 |
|--------|---------|------|
| 用户总数 | `users` 表 COUNT | 系统注册用户数 |
| 角色总数 | `roles` 表 COUNT | 已配置角色数 |
| 功能总数 | `functions` 表 COUNT | 已注册功能节点数 |
| 瞭望源数 | `watch_sources` 表 COUNT | 已配置采集源数 |
| 采集总数 | `watch_results` 表 COUNT | 历史采集总次数 |
| 仓库数据 | `data_warehouse` 表 COUNT | 已保存到仓库的记录数 |
| 模型数量 | `ai_models` 表 COUNT | 已配置 AI 模型数 |
| 采集统计 | 成功/失败/已保存 | 采集结果状态分布 |
| Token 统计 | `ai_models.total_tokens` SUM | 所有模型累计 Token 消耗 |

---

### 8. 前台智能问数系统

#### 8.1 概述

前台智能问数系统（`/chat`）是 v0.3 新增的**普通用户 AI 对话界面**，采用 A/B/C/D/E 五区布局：

```
┌──────────────────┬──────────────────────────────┐
│  A区: LOGO+标题   │                              │
│  B区: 模型选择    │     D区: 对话区               │
│  C区: 任务列表    │   聊天气泡（左AI / 右用户）    │
│                  ├──────────────────────────────┤
│                  │     E区: 输入区               │
│                  │  输入框 + /快捷 + @数字员工    │
└──────────────────┴──────────────────────────────┘
```

#### 8.2 核心功能

| 区域 | 功能 | 说明 |
|------|------|------|
| **A区** | LOGO + 标题 | 品牌标识，显示系统名称和版本 |
| **B区** | 模型切换器 | 下拉选择启用的 AI 模型，⭐标识默认模型 |
| **C区** | 任务列表 | 对话历史自动生成标题，点击切换/删除对话 |
| **D区** | 对话区 | Markdown 渲染气泡（marked.js），左 AI / 右用户 |
| **E区** | 输入区 | 多行输入框 + `@` 数字员工菜单 + `/` 快捷指令 |

#### 8.3 MCP 工具调用与 SSE 流式对话

- **LLM Function Calling 模式**（有 API Key）：LLM 收到消息后自主判断是否需要调用工具，调用后基于真实数据生成回复
- **MCP 语义匹配模式**（无 API Key）：基于 18 个 MCP 工具的名称和描述进行语义评分，自动选择最佳工具执行
- **图表注入**：AI 回复中 `[CHART:...]` 标记自动渲染为 ECharts 图表
- **表格注入**：`[TABLE:...]` 标记自动渲染为 HTML 数据表格
- **元信息显示**：每条 AI 回复下方显示响应时间(s)和 Token 消耗

#### 8.4 对话持久化

- 双表存储：`conversations`（对话元信息）+ `conversation_messages`（消息记录）
- 自动标题：首条消息前 30 字符作为对话标题
- 多轮对话：最近 10 条消息自动注入上下文
- 归属校验：仅对话创建者可查看/删除自己的对话
- 管理侧会话管理：管理员可在 `/admin/conversation` 跨用户查看会话列表、按用户筛选、查看消息详情并强制删除异常会话

#### 8.5 语音合成播报（TTS）

v0.4.1 新增的 **Edge TTS 语音合成播报**功能，为每条 AI 回复消息提供一键朗读能力。

| 特性 | 说明 |
|------|------|
| **引擎** | Microsoft Edge TTS（免费、高质量神经网络语音） |
| **语音** | 6 种中文语音可选（晓晓/云希/云健/晓伊/云扬/晓晨），默认「晓晓」 |
| **触发** | 每条 AI 消息气泡下方显示 🔊 播报按钮，点击即可朗读 |
| **缓存** | 基于文本 MD5 的本地缓存，相同文本不重复生成 |
| **音频** | MP3 格式，流式返回，支持暂停/恢复 |

**使用方式**：
1. 在对话页面（`/chat`）发送消息获取 AI 回复
2. 点击 AI 回复气泡下方的「🔊 播报」按钮
3. 等待语音合成完成（首次约 1-3 秒，缓存命中秒级响应）
4. 自动播放音频；再次点击可停止播放

**后端 API**：`POST /api/chat/tts`
- 参数：`text`（待合成文本，1-4000 字符）、`voice`（可选语音名）
- 返回：`audio/mpeg` 二进制音频流

---

### 9. 技能管理

#### 9.1 概述

技能管理（`/admin/skill`）是 v0.5 新增模块，为数字员工提供**可复用的能力增强框架**。每个技能定义后，数字员工创建时可从技能库中勾选组合。

#### 9.2 技能类型

| 类型 | 实现方式 | 效果 |
|------|----------|------|
| **Prompt 增强** | 存储一段完整的 prompt 指令模板 | LLM 调用 `load_skill` 后注入系统指令，改变行为 |
| **Function 调用** | 映射到一个 MCP 工具（如 `search_warehouse`） | LLM 加载后获知可调用对应工具，形成技能→工具链 |

#### 9.3 按需加载架构

```
用户 @数字员工 提问
    │
    ├─ System Prompt 中嵌入「可用技能」列表（仅名称 + 一句话描述）
    │   例: - 数据搜索: 在数据仓库中按关键词搜索采集结果
    │        - 数据统计: 生成数据仓库统计报告，含图表标记
    │
    └─ LLM 判断需要某技能 → 调用 load_skill(skill_name)
         │
         └─ 返回 Prompt 模板指令 → LLM 遵循执行（模板中可直接描述 MCP 工具用法）
```

#### 9.4 默认技能（5个）

| 技能 | 描述 |
|------|------|
| 📊 **数据统计** | 生成数据仓库统计报告，含图表标记 |
| 🔍 **数据搜索** | 在数据仓库中按关键词搜索采集结果 |
| 📰 **新闻摘要** | 聚合多源新闻并生成结构化摘要 |
| 🕷 **深度采集** | 对指定 URL 进行正文深度抓取 |
| 🌐 **翻译助手** | 高质量中英文双向翻译 |

---

### 10. 数字化员工

#### 9.1 概述

数字化员工（`/admin/employee`）是 v0.3 新增的**AI Agent 管理模块**，支持两种类型：

| 类型 | 实现方式 | 适用场景 |
|------|----------|----------|
| **LLM 型** | 绑定 AI 模型 + 系统提示词 + 技能列表 + MCP 工具权限（含 Crawl4ai 深度采集） | 复杂推理、数据分析、文案撰写、音乐推荐、深度采集 |
| **API 型** | HTTP/HTTPS API + 参数模板 + 响应渲染模板 | 天气查询等外部服务调用 |

#### 9.2 默认数字员工（8个）

| 员工 | 类型 | 核心能力 |
|------|------|---------|
| 🏭 **产业专员** | LLM | 产业链分析、政策解读、竞品分析、趋势预判 |
| 🧠 **天机助手** | LLM | 信息检索、数据分析、文案撰写、代码辅助 |
| 🌤 **天气** | API | 实时天气查询（wttr.in），返回温度/湿度/风力卡片 |
| 🕷 **采集专员** | LLM | 数据仓库搜索、深度采集、内容提取与整理 |
| ✍️ **文案编写** | LLM | 报告撰写、方案策划、公文起草、宣传文案 |
| 📰 **新闻聚合** | LLM | 新闻检索、热点追踪、每日简报 |
| 📚 **科普助手** | LLM | 百科问答、知识科普、概念解释 |
| 🎵 **随机音乐** | LLM (MCP) | 通过 get_random_music 工具调用 Meting API，从网易云热歌榜随机推荐歌曲并展示音乐卡片 |

#### 9.3 调用方式

- **后台测试**：`/admin/employee/test` 对话测试页面（管理员特权模式，绕过 MCP 权限）
- **后台调用**：`POST /admin/employee/invoke` SSE 流式 API
- **前台 @ 触发**：用户在输入框中输入 `@天气 成都` 自动匹配并调用，严格遵循员工的 MCP 工具权限配置
- **数据仓库注入**：LLM 型员工自动注入数据仓库查询结果作为上下文（仅当员工有权使用对应工具时）

#### 9.4 LLM 型员工特性

- **模型回退**：员工绑定模型 → 系统默认模型 → 第一个启用模型
- **MCP 工具权限控制（v0.6.1）**：员工编辑页可勾选允许使用的 MCP 工具，仅勾选且已启用的工具才对员工可用（最小权限原则）。未配置任何工具时，员工无权调用任何 MCP 工具。
- **工具调用**：自动识别意图（数据仓库查询/统计/深度采集）并执行
- **深度采集**：通过 MCP 工具权限控制（勾选「Crawl4ai 智能采集」/「批量深度采集」即可启用）
- **Mock 智能模式**：无 API Key 时提供本地工具调用和结构化回复

---

## API 接口一览

> **基础 URL**: `http://localhost:10010`
> **认证方式**: Tornado Secure Cookie（`username` Cookie）
> **CSRF**: 所有 POST/PUT/DELETE 请求需携带 `_xsrf` token
> **Content-Type**: 表单提交为 `application/x-www-form-urlencoded`

### 认证

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 登录页面 |
| POST | `/` | 提交登录表单 |
| GET | `/register` | 注册页面 |
| POST | `/register` | 提交注册表单 |
| GET | `/logout` | 登出（清除 Cookie，重定向到登录页） |
| GET | `/index` | 前台首页（需登录，普通用户默认跳转） |

### 管理后台 (需管理员权限)

#### 仪表盘
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin` | 管理后台仪表盘首页 |

#### 用户管理
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/user` | 用户列表（`?page=&search=`） |
| GET | `/admin/user/add` | 新增用户页面 |
| POST | `/admin/user/add` | 提交新增用户 |
| GET | `/admin/user/edit` | 编辑用户页面（`?id=`） |
| POST | `/admin/user/edit` | 提交编辑用户 |
| POST | `/admin/user/delete` | 删除用户 |
| POST | `/admin/user/toggle` | 启用/禁用切换 |
| POST | `/admin/user/batch-delete` | 批量删除 |
| POST | `/admin/user/batch-toggle` | 批量启用/禁用 |

#### 角色管理
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/role` | 角色列表 |
| GET | `/admin/role/add` | 新增角色页面 |
| POST | `/admin/role/add` | 提交新增角色 |
| GET | `/admin/role/edit` | 编辑角色页面（`?id=`） |
| POST | `/admin/role/edit` | 提交编辑角色 |
| POST | `/admin/role/delete` | 删除角色 |

#### 功能管理
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/function` | 功能列表（树形展示） |
| GET | `/admin/function/add` | 新增功能页面 |
| POST | `/admin/function/add` | 提交新增功能 |
| GET | `/admin/function/edit` | 编辑功能页面（`?id=`） |
| POST | `/admin/function/edit` | 提交编辑功能 |
| POST | `/admin/function/delete` | 删除功能 |
| POST | `/admin/function/toggle` | 启用/禁用功能 |

#### 菜单管理
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/menu` | 按角色预览菜单树（`?role_id=`） |
| POST | `/admin/menu/sort` | 菜单排序（上移/下移） |

#### 瞭望采集
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/watch` | 瞭望采集页 + 历史结果（`?keyword=&page=&source_id=`） |
| POST | `/admin/watch` | 执行采集，返回 JSON（`keyword=&source_ids=&page=`） |
| GET | `/admin/watch/stream` | SSE 实时采集进度（`event: collect_progress`） |
| GET | `/admin/watch/log` | 采集日志页（从 `audit_logs` 读取 `*COLLECT*` 记录） |
| POST | `/admin/watch/save` | 保存采集结果到数据仓库 |
| POST | `/admin/watch/deep-collect` | 一站式深度采集 |

#### 瞭望源管理
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/watch/source` | 瞭望源列表 |
| GET | `/admin/watch/source/add` | 新增瞭望源页面 |
| POST | `/admin/watch/source/add` | 提交新增瞭望源 |
| GET | `/admin/watch/source/edit` | 编辑瞭望源页面（`?id=`） |
| POST | `/admin/watch/source/edit` | 提交编辑瞭望源 |
| POST | `/admin/watch/source/delete` | 删除瞭望源 |
| POST | `/admin/watch/source/toggle` | 启用/禁用瞭望源 |

#### 数据仓库
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/warehouse` | 数据仓库列表（`?page=&keyword=&source_id=`） |
| GET | `/admin/warehouse/detail` | 查看详情（`?id=`） |
| POST | `/admin/warehouse/delete` | 删除单条记录 |
| POST | `/admin/warehouse/batch-delete` | 批量删除 |
| POST | `/admin/warehouse/deep-collect` | 深度采集指定记录 |

#### 模型引擎
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/model` | 模型列表（`?page=&category=`） |
| GET | `/admin/model/add` | 新增模型页面 |
| POST | `/admin/model/add` | 提交新增模型 |
| GET | `/admin/model/edit` | 编辑模型页面（`?id=`） |
| POST | `/admin/model/edit` | 提交编辑模型 |
| POST | `/admin/model/delete` | 删除模型 |
| POST | `/admin/model/toggle` | 启用/禁用模型 |
| POST | `/admin/model/default` | 设为默认模型 |
| GET | `/admin/api/model/list` | 模型 JSON API（返回已启用模型列表） |

#### 管理侧会话管理（Issue #17）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/conversation` | 所有用户会话列表，支持 `?username=&keyword=&page=&id=` 筛选/查看详情 |
| POST | `/admin/conversation/delete` | 管理员删除任意会话及其消息 |

#### 接口管理（Issue #26）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/interface` | 接口模板列表（`?page=&keyword=`） |
| GET/POST | `/admin/interface/add` | 新增接口模板 |
| GET/POST | `/admin/interface/edit` | 编辑接口模板（`?id=`） |
| POST | `/admin/interface/delete` | 删除接口模板 |
| POST | `/admin/interface/toggle` | 启用/禁用接口模板 |
| POST | `/admin/interface/test` | 测试接口模板（保存接口或表单草稿） |
| GET | `/admin/api/interface/list` | 已启用接口模板 JSON API（供 API 型数字员工联动） |

#### 数字化员工（v0.3）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/employee` | 员工列表（卡片式，`?page=&type=`） |
| GET | `/admin/employee/add` | 新增员工页面 |
| POST | `/admin/employee/add` | 提交新增员工 |
| GET | `/admin/employee/edit` | 编辑员工页面（`?id=`） |
| POST | `/admin/employee/edit` | 提交编辑员工 |
| POST | `/admin/employee/delete` | 删除员工 |
| POST | `/admin/employee/toggle` | 启用/禁用员工 |
| POST | `/admin/employee/invoke` | **SSE 流式调用员工** |
| GET | `/admin/api/employee/list` | 员工 JSON API |
| GET | `/admin/employee/test` | 员工对话测试页 |

#### 用户前台-智能问数（v0.3）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/chat` | 用户前台对话主页（A/B/C/D/E 五区） |
| POST | `/chat/stream` | **SSE 流式 AI 对话** |
| POST | `/chat/employee/invoke` | **SSE 流式 @数字员工调用** |
| GET | `/api/chat/models` | 获取可用模型列表 |
| GET | `/api/chat/employees` | 获取数字员工列表 |
| GET | `/api/chat/conversation/list` | 用户对话历史列表 |
| POST | `/api/chat/conversation/create` | 创建新对话 |
| POST | `/api/chat/conversation/delete` | 删除对话 |
| GET | `/api/chat/conversation/messages` | 获取对话消息（`?id=`） |

---

## 数据库设计

### ER 关系图

```mermaid
erDiagram
    users ||--o| roles : "role_id"
    roles ||--o{ role_functions : "role_id"
    functions ||--o{ role_functions : "function_id"
    functions ||--o| functions : "parent_id"
    watch_sources ||--o{ watch_results : "source_id"
    watch_results ||--o| data_warehouse : "result_id"
    api_interfaces ||--o{ digital_employees : "api_interface_id"
    mcp_tools ||--o{ digital_employees : "mcp_tool_ids"
    mcp_tools ||--o| skills : "mcp_tool_id"
    audit_logs {
        int id PK
        string action
        string username
        string target
        string detail
        string client_ip
        timestamp created_at
    }
    ai_models {
        int id PK
        string name
        string provider
        string api_base
        string api_key
        string model_name
        string category
        string system_prompt
        real temperature
        real top_p
        int top_k
        int max_tokens
        int context_size
        int total_tokens
        int is_enabled
        int is_default
        timestamp created_at
    }
    data_warehouse {
        int id PK
        int result_id FK
        string title
        string link
        string summary
        string source_name
        string raw_data
        int is_deep_collected
        timestamp deep_collected_at
        timestamp created_at
    }
    conversations {
        int id PK
        string username
        string title
        int model_id
        timestamp created_at
        timestamp updated_at
    }
    conversation_messages {
        int id PK
        int conversation_id FK
        string role
        string content
        int token_count
        timestamp created_at
    }
    api_interfaces {
        int id PK
        string name
        string api_url
        string api_method
        string api_headers
        string api_params_template
        string response_render_template
        string api_secret
        int is_enabled
        int sort_order
        timestamp created_at
        timestamp updated_at
    }
    digital_employees {
        int id PK
        string name
        string employee_type
        string description
        int model_id
        string system_prompt
        string skills
        int crawl4ai_enabled      // [v0.6.1 废弃] 改用 mcp_tool_ids
        string mcp_tool_ids        // [v0.6.1] MCP 工具权限 JSON 数组 "[1,2,3]"
        string api_url
        string api_method
        string api_headers
        string api_params_template
        string response_render_template
        string api_secret
        int api_interface_id
        int is_enabled
        timestamp created_at
    }
    mcp_tools {
        int id PK
        string name UK
        string display_name
        string description
        string category
        string tool_type
        string handler_module
        string input_schema
        int is_enabled
        int is_system
        int sort_order
    }
    mcp_tool_test_logs {
        int id PK
        int tool_id FK
        string test_params
        string test_result
        int is_success
        int duration_ms
        timestamp created_at
    }
    skills {
        int id PK
        string name UK
        string description
        string prompt_template
        int mcp_tool_id FK
        int is_enabled
    }
```

### 核心表清单

| 表名 | 说明 | 预期记录数 | 主要索引 |
|------|------|-----------|---------|
| `users` | 用户表 | 10 ~ 1000 | `username`(UNIQUE), `role_id` |
| `roles` | 角色表 | 3 ~ 50 | `name`(UNIQUE) |
| `functions` | 功能/菜单项 | 10 ~ 100 | `parent_id` |
| `role_functions` | 角色-功能关联（中间表） | N×M | `role_id`, `function_id` (联合主键) |
| `watch_sources` | 瞭望源配置 | 3 ~ 50 | `is_enabled` |
| `watch_results` | 原始采集结果 | 100 ~ 100000 | `source_id` |
| `data_warehouse` | 独立数据仓库 | 100 ~ 100000 | `link`(UNIQUE) |
| `ai_models` | AI 模型配置 | 3 ~ 50 | `is_default` |
| `api_interfaces` | API 接口模板 | 3 ~ 100 | `name`(UNIQUE), `is_enabled` |
| `audit_logs` | 操作审计日志 | 自动增长 | `action`, `username`, `created_at` |
| `conversations` | 对话元信息表 | 10 ~ 10000 | `username` |
| `conversation_messages` | 对话消息表 | 100 ~ 100000 | `conversation_id` (CASCADE) |
| `digital_employees` | 数字化员工配置表 | 5 ~ 50 | `is_enabled` |
| `mcp_tools` | MCP 工具注册表（v0.4.2） | 18 ~ 100 | `name`(UNIQUE), `category` |
| `mcp_tool_test_logs` | MCP 工具测试日志（v0.4.2） | 自动增长 | `tool_id`(CASCADE) |
| `skills` | 技能库表（v0.5.0） | 5 ~ 100 | `name`(UNIQUE), `mcp_tool_id` |

> 完整 DDL 和字段详细说明请参考 `docs/constraint.md`。

### 数据库特性

- **WAL 模式**：`PRAGMA journal_mode=WAL` — 支持并发读写，写入不阻塞读取
- **外键约束**：`PRAGMA foreign_keys=ON` — 确保数据完整性
- **自动建表**：`init_db()` 使用 `CREATE TABLE IF NOT EXISTS`，首次启动自动创建
- **自动迁移**：兼容旧表结构，通过 `ALTER TABLE ADD COLUMN` 向后兼容添加新字段
- **种子数据**：`seed_default_data()` 检查已有数据，幂等插入默认角色和管理员账户

---

## 安全设计

### 防护体系总览

| 防护项 | 实现方式 | 参考标准 |
|--------|---------|---------|
| **密码存储** | PBKDF2-SHA256（60 万轮迭代 + 16 字节随机盐，hex 存储） | OWASP 2023 |
| **CSRF** | Tornado `xsrf_cookies=True` 全局开启 + 模板 `{% module xsrf_form_html() %}` | OWASP A01:2021 |
| **XSS** | Tornado 模板默认 HTML 转义 + 采集内容清洗（`unescape` + 标签剥离） | OWASP A03:2021 |
| **SQL 注入** | 全参数化查询（`?` 占位符），0 处字符串拼接 SQL | OWASP A03:2021 |
| **SSRF** | URL 协议白名单 + 内网 IP 段拦截 + DNS 解析校验 + CRLF 检测；接口管理/ API 型员工调用使用安全 HTTP 客户端固定已校验 IP 且不自动跟随重定向 | OWASP A10:2021 |
| **接口密钥与 Header** | `api_secret` 加密存储；接口联动 API 不回显密钥，`Authorization` / `Cookie` / `X-API-Key` 等敏感 Header 脱敏展示 | OWASP |
| **Header 注入** | CR/LF 字符检测（`has_crlf()`），拒绝含 `\r` `\n` 的输入 | OWASP A03:2021 |
| **安全响应头** | CSP / X-Frame-Options / X-Content-Type-Options / X-XSS-Protection / Referrer-Policy / Permissions-Policy | OWASP |
| **登录限速** | IP + 用户名维度，5 次失败 / 15 分钟锁定窗口 | OWASP A07:2021 |
| **审计日志** | 关键操作全量写入 `audit_logs` 表（含时间、IP、操作详情） | OWASP A09:2021 |
| **Clickjacking** | `X-Frame-Options: DENY` + CSP `frame-ancestors 'none'` | OWASP A05:2021 |

### SSRF 防护详情

```
validate_url_safe(url)
    ├── 协议白名单检查: 仅允许 http / https
    ├── CRLF 检测: 拒绝含 \r \n 的 URL（防止 HTTP Request Smuggling）
    ├── DNS 解析: hostname → IP 地址
    └── IP 黑名单检查 (CIDR):
        ├── 127.0.0.1 / localhost / 0.0.0.0 / ::1     （回环地址）
        ├── 10.0.0.0/8                                 （A 类私有）
        ├── 172.16.0.0/12                              （B 类私有）
        ├── 192.168.0.0/16                             （C 类私有）
        ├── 169.254.0.0/16                             （链路本地）
        └── 100.64.0.0/10                              （运营商级 NAT）
```

### 安全响应头

实际发送的 HTTP 响应头：

```
Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https:; font-src 'self' https://cdn.jsdelivr.net; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: camera=(), microphone=(), geolocation=()
```

---

## 配置说明

### 配置文件

所有配置集中在 `app/config/settings.py` 的 `Settings` 类中，**全部支持环境变量覆盖**，无需修改代码即可适配开发/测试/生产环境。

### 配置项速查

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `COOKIE_SECRET` | 随机生成 | 安全 Cookie 签名密钥（**生产环境必须设置**，否则重启后所有会话失效） |
| `DB_PATH` | `database/finderos.db` | SQLite 数据库文件路径（相对路径基于项目根目录） |
| `PORT` | `10010` | HTTP 服务监听端口 |
| `DEBUG` | `false` | 调试模式（`true` 时开启 Tornado 调试功能和自动重载） |
| `PBKDF2_ITERATIONS` | `600000` | PBKDF2-SHA256 密码哈希迭代次数（OWASP 2023 推荐 ≥ 600,000） |
| `PAGE_SIZE` | `20` | 列表默认分页大小 |
| `LOGIN_MAX_FAILURES` | `5` | 登录失败次数上限（同一 IP + 用户名组合） |
| `LOGIN_LOCKOUT_SECONDS` | `900` | 登录锁定时间（秒），默认 15 分钟 |
| `BIND_ADDRESS` | `127.0.0.1` | HTTP 服务监听地址（`0.0.0.0` 监听所有网卡） |

### 生产环境启动示例

```bash
# Linux / macOS
export COOKIE_SECRET="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
export DEBUG=false
python main.py

# Windows PowerShell
$env:COOKIE_SECRET = -join ((48..57)+(65..90)+(97..122) | Get-Random -Count 64 | ForEach-Object {[char]$_})
$env:DEBUG = "false"
python main.py
```

> ⚠️ **安全警告**：生产环境**必须**通过环境变量设置 `COOKIE_SECRET`，否则每次重启会生成随机密钥导致所有用户会话失效。`DEBUG` 模式在生产环境必须关闭，否则会在前端暴露 Python 堆栈跟踪。

### 生产环境推荐配置

```bash
export COOKIE_SECRET="<生成的64位随机字符串>"
export DEBUG=false
export PBKDF2_ITERATIONS=600000
export LOGIN_MAX_FAILURES=3
export LOGIN_LOCKOUT_SECONDS=1800
python main.py
```

---

## 数据库迁移

当系统升级添加新字段/新表时，运行迁移脚本以保持数据库结构同步：

```bash
# 执行所有待处理的迁移
python migrate_db.py

# 查看迁移状态
python migrate_db.py --status
```

### 迁移历史

| 版本 | 变更内容 |
|------|---------|
| v0.2.5 | 添加 `ai_models.total_tokens` 列（Token 消耗累加统计） |
| v0.2.5 | 添加 `audit_logs` 表（操作审计日志，含 3 个索引） |
| v0.2.5 | 添加安全相关索引（`audit_logs.action`、`audit_logs.username`、`audit_logs.created_at`） |
| v0.2.13 | 添加 `data_warehouse` 独立表（标题/链接/摘要/来源 + URL 去重索引） |
| v0.3.0 | 添加 `conversations` / `conversation_messages` 表（多轮对话持久化） |
| v0.3.0 | 添加 `digital_employees` 表（数字化员工配置） |
| v0.3.0 | 添加 `data_warehouse_fts` 虚拟表 + 3 个同步触发器（FTS5 全文检索） |
| v0.4.1 | 添加 `api_interfaces` 表与 `digital_employees.api_interface_id`（接口管理联动） |
| v0.4.2 | 添加 `mcp_tools` / `mcp_tool_test_logs` 表 + `skills.mcp_tool_id` / `digital_employees.mcp_tool_ids` 列 |
| v0.4.2 | 种子数据迁移：18 个内置 MCP 工具 + 旧 TAG → Skill ID 数据迁移 |

> 迁移脚本具有**幂等性**：重复执行不会破坏已有数据。使用 `ALTER TABLE ADD COLUMN`（列不存在时静默跳过）和 `CREATE TABLE IF NOT EXISTS` 确保安全。

---

## 开发指南

### 添加新业务模块

以添加一个新模块（例如"公告管理"）为例，需要创建/修改以下文件：

| 步骤 | 文件 | 操作 |
|------|------|------|
| 1 | `app/models/announcement.py` | 新建 Repository 类（静态方法：CRUD + 分页查询） |
| 2 | `app/models/db.py` → `init_db()` | 添加 `CREATE TABLE IF NOT EXISTS announcements (...)` |
| 3 | `app/controllers/admin_announcement.py` | 新建 Handler，继承 `AdminBaseHandler` |
| 4 | `app/templates/admin/announcement_list.html` | 新建模板，`{% extends "admin/base_layout.html" %}` |
| 5 | `main.py` → `make_app()` | 添加路由 `(r"/admin/announcement", AnnouncementListHandler)` |
| 6 | 后台 → 功能管理 | 新增功能节点（名称 + 图标 + 路由 + 排序） |
| 7 | 后台 → 角色管理 | 为管理员角色勾选新功能的访问权限 |

### 代码规范

- **Controller 层**：参数校验 → 业务调用 → 视图渲染，保持简洁。不包含复杂业务逻辑。
- **Model 层**：纯数据访问，使用 Repository 模式，所有方法为 `@staticmethod`。不包含业务逻辑。
- **Service 层**：复杂业务逻辑（如采集引擎 `collector.py`），可复用的独立组件。
- **数据库操作**：**必须**使用参数化查询（`?` 占位符），**严禁**字符串拼接 SQL。
- **模板继承**：后台页面**必须**继承 `admin/base_layout.html`，自动包含侧边栏和顶栏布局。
- **安全校验**：后台 Handler **必须**继承 `AdminBaseHandler`（自动进行权限校验），前台 Handler 继承 `BaseHandler`。
- **命名规范**：Handler 类名使用 `XxxHandler` 后缀，Repository 类名使用 `XxxRepository` 后缀。

### 常用命令

```bash
# 激活虚拟环境 (Windows)
.venv\Scripts\activate

# 激活虚拟环境 (macOS/Linux)
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 启动开发服务器（默认端口 10010）
python main.py

# 切换端口启动
# Windows PowerShell:
$env:PORT = "8080"; python main.py
# Linux/macOS:
PORT=8080 python main.py

# 开启调试模式（自动重载 + 详细错误）
# Windows PowerShell:
$env:DEBUG = "true"; python main.py
# Linux/macOS:
DEBUG=true python main.py

# 运行数据库迁移
python migrate_db.py

# 创建/重置管理员账号
python make_admin.py --username admin --password mypassword

# 列出所有用户
python make_admin.py --list

# 重置管理员密码
python make_admin.py --reset --username admin --password newpassword
```

### 调试技巧

1. **查看 Tornado 日志**：终端直接输出结构化日志（时间戳 + 级别 + 消息）
2. **数据库调试**：使用任意 SQLite 客户端打开 `database/finderos.db`，如 [DB Browser for SQLite](https://sqlitebrowser.org/)
3. **前端调试**：浏览器 F12 → Network 面板可查看 SSE 事件流
4. **审计追踪**：查询 `audit_logs` 表可追溯所有关键操作

---

## 默认账户

| 用户名 | 密码 | 角色 | 后台权限 | 说明 |
|--------|------|------|---------|------|
| `admin` | `admin888` | 系统管理员 | ✅ 全部功能 | 不可删除/禁用自身 |

> ⚠️ **首次登录后请立即修改默认密码！** 可使用管理后台的用户编辑功能或 `make_admin.py --reset` 命令。

---

## 测试用例

系统已覆盖 7 大模块共 30+ 项测试用例，详见 `docs/test_case.md`：

| 模块 | 测试项数 | 覆盖要点 |
|------|---------|---------|
| **认证模块** | 6 | 正确登录、错误密码、空表单、登录限速触发、未登录拦截、登出 |
| **用户管理** | 6 | 新增用户、编辑用户、禁用/启用、删除、关键词搜索、admin 账号保护 |
| **角色管理** | 3 | 新增角色+功能授权、系统角色编辑保护（is_system）、系统角色删除保护 |
| **瞭望采集** | 9 | 关键词采集、瞭望源选择、保存到数据仓库、SSRF 防护、空关键词、SSE 进度事件、进度条渲染、采集审计日志、日志页检索 |
| **模型引擎** | 6 | 新增模型、设为默认、Mock 对话（无 API Key）、真实 API 流式对话、Token 统计、审计日志记录 |
| **会话管理** | 5 | 跨用户列表、用户筛选、消息详情、管理员删除、用户侧隔离保持 |
| **接口管理** | 10 | 接口模板 CRUD、安全校验、敏感 Header 脱敏、安全 HTTP 调用、接口测试、API 型数字员工联动创建 |
| **MCP 重构** | 6 | 工具表查询、CRUD、注册表加载、员工权限、技能关联、测试日志 |
| **安全测试** | 5 | XSS 注入（采集内容）、SQL 注入（参数化查询验证）、CSRF Token 校验、密码哈希强度、安全响应头存在性 |

### 运行测试

```bash
# 运行全部测试
python -m pytest test/ -v

# 运行单个测试文件
python -m pytest test/test_user_models.py -v

# 运行 Issue #26 接口管理测试
python -m pytest test/test_issue26_api_interface.py -v

# 运行 Issue #24 采集进度与日志测试
python -m pytest test/test_issue24_collect_progress.py -v

# 运行 Issue #17 管理侧会话管理测试
python -m pytest test/test_issue17_admin_conversation.py -v

# 运行单个测试方法
python -m pytest test/test_login_rate_limiter.py::TestLoginRateLimiter::test_rate_limit -v
```

---

## 更新日志

### v0.4.2 (2026-07-15) — MCP 重构完成

- 🔧 **MCP 工具种子数据**：18 个内置工具迁移至数据库驱动，含完整 description 和 input_schema
- 🏷️ **三色徽章系统**：员工卡片区分 MCP 工具（蓝色 `.mcp-tag`）、Skill（绿色 `.skill-tag`）、旧 TAG（橙黄 `.legacy-tag`）
- 🗑️ **crawl4ai_enabled 废弃**：改为通过 MCP 工具 `collect_with_crawl4ai` / `batch_deep_collect` 控制
- 🔗 **Skill 绑定 MCP 工具**：技能表单新增 MCP 工具下拉选择器，`mcp_tool_id` 关联
- 🔄 **旧 TAG 迁移**：`migrate_legacy_tags_to_skills_v042` 将员工旧格式字符串标签转换为 Skill ID 数组
- 🔐 **SSRF 防护增强**：crawl4ai 工具新增 `validate_url_safe` URL 安全校验
- 📋 **员工前端增强**：`UserEmployeeListHandler` API 返回三色徽章数据
- 🧪 **测试覆盖**：6 项测试全部通过（工具查询/CRUD/注册表/员工权限/技能关联/测试日志）

### v0.4.1 (2026-07) — 管理侧接口管理（Issue #26）

- 🔗 **接口管理模块**：新增 `/admin/interface` 接口模板 CRUD、启用/禁用、列表搜索与接口测试。
- 🧩 **数字员工联动**：API 型员工表单可选择接口模板，自动填充 URL / Method / Headers / Params / Response Template。
- 🔐 **密钥安全**：接口密钥加密入库，联动创建员工时服务端复用；敏感 Header 脱敏展示并支持安全恢复。
- 🛡️ **安全 HTTP 调用**：接口测试与 API 型员工调用共用安全 HTTP 工具，拒绝内网地址、固定已校验 DNS 解析结果、禁止自动重定向并校验 Header/Host。
- 🧪 **测试补充**：新增 `test/test_issue26_api_interface.py` 覆盖接口模板、校验、安全调用和员工关联。

### v0.4.1 (2026-07-15) — UI 显示修复

- 🐛 **修复员工卡片模型名称显示 "None"**：`model_name` 为 `None` 时模板默认值回退不生效，改用 `or` 运算符确保正确显示"默认模型"
- 🐛 **修复员工卡片技能标签显示为 dict 字符串**：技能 ID 解析后返回 dict 列表但模板直接渲染为 Python 字面量，改为提取 `name` 字段作为字符串列表
- 🐛 **修复员工对话中技能名称 join 异常**：`skills_list` 为 int ID 数组时 `"、".join()` 会抛出 TypeError，增加 ID→名称解析逻辑

### v0.4.1 (2026-07) — TTS 语音合成播报

- 🔊 **Edge TTS 语音播报**：AI 回复消息一键朗读，使用 Microsoft Edge 免费 TTS 服务
- 🎙️ **6 种中文语音**：晓晓/云希/云健/晓伊/云扬/晓晨，默认「晓晓」神经网络语音
- 💾 **智能缓存**：基于文本 MD5 的本地缓存，相同文本不重复生成
- ⏯️ **播放控制**：点击播报开始播放，再次点击停止；支持暂停/恢复
- 🔒 **安全审计**：TTS 调用写入 `audit_logs` 表（`USER_TTS`）
- 🎨 **前端交互**：气泡下方显示 🔊 播报按钮，加载动画 + 播放状态指示

### v0.4 (2026-07) — MCP 协议架构重构

- 🔌 **MCP 协议模块**：新增 `app/mcp/` 完整实现（Server / Client / Tools）
- 🔧 **9 个 MCP 工具**：search_warehouse / get_recent_warehouse_data / get_warehouse_stats / deep_collect_url / collect_web_data / list_digital_employees / get_random_music / list_conversations / get_conversation_messages
- 🤖 **LLM Function Calling**：有 API Key 时 LLM 自主决策工具调用（Tool → Execute → Reply 闭环，最多 3 轮）
- 🧠 **MCP 语义匹配**：无 API Key 时基于工具描述的多维语义评分自动路由，替代旧关键词硬匹配
- 🗑️ **废弃旧代码**：移除 `_detect_intent_and_query` 及 50+ 硬编码关键词意图识别逻辑
- 🆕 **/tools 指令**：输入 `/tools` 查看所有可用 MCP 工具列表
- 📝 **工具结果格式化**：`_format_tool_result_as_reply` 将工具 JSON 转为自然语言 Markdown 回复

### v0.3 (2026-07) — 前台智能问数系统

**v0.3.0** — 用户前台 + 数字员工 + ECharts 报表
- ✅ **前台智能问数**：A/B/C/D/E 五区布局对话页面（`/chat`）
- ✅ **SSE 流式对话**：真实 API + Mock 回退，Markdown 气泡渲染
- ✅ **多轮对话**：`conversations` + `conversation_messages` 双表持久化
- ✅ **@数字员工**：7 个默认员工（天气/采集专员/文案编写/新闻聚合/科普助手/产业专员/天机助手）
- ✅ **LLM 型员工**：模型绑定 + 提示词 + 技能 + 数据仓库上下文注入
- ✅ **API 型员工**：HTTP 调用 + 参数模板 + 响应渲染模板（天气卡片）
- ✅ **ECharts 报表**：柱状图/折线图/饼图/散点图 + 数据表格
- ✅ **图表指令**：`[CHART:...]` / `[TABLE:...]` 标记自动注入系统提示
- ✅ **模型切换**：用户前台 B 区下拉选择模型
- ✅ **任务列表**：用户前台 C 区对话历史管理
- ✅ **首页改造**：普通用户登录后自动跳转 `/chat`
- ✅ **员工管理后台**：卡片式列表 + 表单编辑 + 测试对话页
- ✅ **深度采集引擎**：正文提取（article/main/body） + crawl4ai 可选增强
- ✅ **定时采集调度器**：基于 Tornado PeriodicCallback 的自动采集

### v0.2.x (2026-07) — 数据采集与 AI 引擎

**v0.2.13** — 数据仓库独立化
- ✅ 新增独立 `data_warehouse` 表（标题/链接/摘要/来源 + URL 去重索引）
- ✅ `DataWarehouseRepository` 仓储层实现
- ✅ 仓库详情页使用字典访问替代 `sqlite3.Row.get()` 方法

**v0.2.12** — 菜单排序与审计增强
- ✅ 菜单排序功能（上移/下移，修改 `sort_order`）
- ✅ 审计日志表索引优化（`action` / `username` / `created_at`）

**v0.2.5** — 安全与统计增强
- ✅ `ai_models.total_tokens` 列（Token 消耗累加统计）
- ✅ `audit_logs` 审计日志表（含 3 个索引）
- ✅ 登录/登出/锁定/对话等关键操作审计记录

**v0.2.0** — Day6-2 扩展模块
- ✅ **瞭望采集引擎**：百度新闻/搜狗新闻/通用解析器，URL 模板占位符，Cookie 预热反爬
- ✅ **瞭望源管理**：CRUD + 启用/禁用，自定义 Request Headers
- ✅ **数据仓库**：采集结果统一存储、关键词检索、批量管理
- ✅ **AI 模型引擎**：多 Provider（OpenAI/DeepSeek/智谱/文心/自定义），6 大分类
- ✅ **SSE 流式对话**：真实 API + 本地 Mock 回退，Token 消耗追踪
- ✅ **SSRF 防护**：协议白名单 + 内网 IP 段拦截 + DNS 解析校验 + CRLF 检测
- ✅ **安全响应头**：OWASP 推荐全量响应头（CSP/X-Frame/HSTS 等）
- ✅ **模型 JSON API**：`GET /admin/api/model/list` 供外部调用

### v0.1 (2026-07) — 基础框架

- ✅ **权限管理子系统**：用户/角色/功能/菜单完整 CRUD
- ✅ **RBAC 权限模型**：用户→角色→功能，两级树形功能结构
- ✅ **登录认证**：PBKDF2-SHA256 60 万轮 + 登录频率限速
- ✅ **管理后台**：Layui 2.x UI，三区布局（搜索+表格+分页）
- ✅ **系统保护**：admin 账号保护、系统角色保护（is_system）、功能禁用级联
- ✅ **安全基础**：CSRF 防护、SQL 注入防护、XSS 防护
- ✅ **种子数据**：自动建表 + 默认角色/管理员/功能菜单

---

## 许可证

本项目仅用于学习和内部使用。

---

> 📚 **相关文档**：
> - 系统设计：`docs/design.md`
> - 需求文档：`docs/requirement.md`
> - API 文档：`docs/api.md`
> - 开发约束：`docs/constraint.md`
> - 测试用例：`docs/test_case.md`
> - 审计报告（修复前）：`docs/audit_report_v1.md`
> - 安全修复报告（修复后）：`docs/audit_report_v2.md`
