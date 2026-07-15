# 全局约束 (constraint.md)

> 本文档用于约束当前项目的全局开发规范与技术边界。请随代码变更同步更新。

## 1. 技术约束

- **语言**: Python 3.11+ (venv 中的解释器版本，推荐 3.13+)
- **Web 框架**: Tornado (`tornado.web` / `tornado.ioloop` / `tornado.httpserver`)
- **数据库**: SQLite3 (`sqlite3` 内置模块，零外部依赖)，DB 文件 `database/finderos.db`
- **模板**: Tornado 原生模板 (`{% extends %}` / `{% block %}` / `{% module xsrf_form_html() %}`)
- **前端**: Layui 2.x + 原生 HTML + CSS + JS (未引入构建工具与前端框架)
- **虚拟环境**: `.venv/`；一切依赖安装与运行必须激活 venv

## 2. 运行约束

- 入口文件: `main.py`
- 监听端口: `10010`
- 启动命令:
  ```bash
  # macOS / Linux:
  source .venv/bin/activate
  # Windows:
  # .venv\Scripts\activate
  python main.py
  ```
- 启动前 `init_db()` 自动创建表结构，`seed_default_data()` 插入种子数据（默认管理员账号/角色/功能），无需手动建库

## 3. 目录约束

| 目录 | 用途 | 变更规则 |
|------|------|---------|
| `app/controllers/` | Controller 层，一个业务一个文件 | 新增业务需新建文件 |
| `app/models/` | Model 层，Repository 模式 | 每个表一个文件 |
| `app/mcp/` | MCP 协议模块（Server/Client/Tools） | MCP 工具变更需同时更新 tools.py |
| `app/services/` | 业务服务层（采集/深度采集/调度） | 独立可复用组件 |
| `app/templates/` | Tornado 原生模板 | 按模块分目录 |
| `app/templates/admin/` | 管理后台模板 | 继承 `base_layout.html` |
| `app/static/` | 静态资源 (CSS/JS/图片) | 按类型分目录 |
| `docs/` | 项目文档 | 自动维护 |

## 4. 安全规范

- `set_secure_cookie`: `xsrf_cookies=True` + 模板 `{% module xsrf_form_html() %}`
- SQL 注入防护: 全部使用 `?` 参数占位符
- 密码存储: 服务端 PBKDF2-SHA256 600K 轮 + 随机盐
- 登录拦截: `login_url="/"` + `@tornado.web.authenticated`
- 管理员权限: 继承 `AdminBaseHandler`，prepare() 中校验用户是否有关联的后台功能权限（非硬编码角色名）
- 系统角色保护: `is_system=1` 的角色不允许编辑/删除
- 超级管理员保护: `admin` 用户不允许禁用/删除；任何管理员均不可禁用/删除自身

## 5. 数据模型

### users 表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| username | TEXT UNIQUE NOT NULL | 用户名 |
| password_hash | TEXT NOT NULL | PBKDF2 哈希 |
| salt | TEXT NOT NULL | 随机盐(hex) |
| role_id | INTEGER FK→roles.id | 角色ID |
| is_enabled | INTEGER DEFAULT 1 | 启用状态(0/1) |
| created_at | TIMESTAMP | 创建时间 |

### roles 表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| name | TEXT UNIQUE NOT NULL | 角色名称 |
| description | TEXT DEFAULT '' | 角色描述 |
| is_system | INTEGER DEFAULT 0 | 系统角色(1=不可删除/编辑) |
| created_at | TIMESTAMP | 创建时间 |

### functions 表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| name | TEXT NOT NULL | 功能名称 |
| icon | TEXT DEFAULT '' | Layui 图标类名 |
| route_path | TEXT DEFAULT '' | 路由地址 |
| parent_id | INTEGER DEFAULT NULL | 父功能ID(NULL=一级) |
| sort_order | INTEGER DEFAULT 0 | 排序 |
| is_enabled | INTEGER DEFAULT 1 | 启用状态 |
| created_at | TIMESTAMP | 创建时间 |

### role_functions 表
| 字段 | 类型 | 说明 |
|------|------|------|
| role_id | INTEGER PK FK→roles.id | 角色ID |
| function_id | INTEGER PK FK→functions.id | 功能ID |

## 6. 权限体系

- **用户 ↔ 角色**: 1对1
- **角色 ↔ 功能**: 多对多（通过 role_functions 中间表）
- **默认角色**: 系统管理员(可访问后台) / 普通用户(仅前台)
- **菜单生成**: 角色 → role_functions → functions → 按 parent_id 构建树形菜单

## 7. 扩展模块 (v0.4.0)

### watch_sources 表（瞭源管理）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| name | TEXT NOT NULL | 瞭望源名称 |
| description | TEXT DEFAULT '' | 描述 |
| url_template | TEXT NOT NULL | URL模板（支持{keyword}/{page}占位符） |
| request_headers | TEXT DEFAULT '{}' | HTTP请求头（JSON格式） |
| is_enabled | INTEGER DEFAULT 1 | 启用状态 |
| sort_order | INTEGER DEFAULT 0 | 排序 |
| schedule_interval | INTEGER DEFAULT 0 | 定时采集间隔（分钟，0=不启用，v0.4.0 迁移新增） |
| created_at | TIMESTAMP | 创建时间 |

### watch_results 表（采集结果记录）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| source_id | INTEGER FK | 瞭望源ID |
| keyword | TEXT | 采集关键词 |
| request_url | TEXT DEFAULT '' | 实际请求URL（通过 `WHERE request_url != ''` 部分唯一索引去重） |
| response_status | INTEGER | 响应状态码 |
| response_size | INTEGER | 响应数据大小（字节） |
| result_data | TEXT DEFAULT '' | 响应数据内容（JSON 格式存储结构化采集结果） |
| created_at | TIMESTAMP | 采集时间 |

> **注意**：本表存储每次采集的原始记录。标记保存后的结构化数据存入独立的 `data_warehouse` 表。

### ai_models 表（模型引擎）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| name | TEXT NOT NULL | 模型名称 |
| provider | TEXT DEFAULT 'openai' | 提供商（openai/deepseek/zhipu/baidu/custom） |
| api_base | TEXT DEFAULT '' | API Base URL |
| api_key | TEXT DEFAULT '' | API密钥（Fernet 对称加密存储） |
| model_name | TEXT DEFAULT '' | 模型标识 |
| category | TEXT DEFAULT 'text' | 分类（text/image/audio/video/multimodal/embedding） |
| system_prompt | TEXT DEFAULT '' | 系统提示词 |
| temperature | REAL | 温度参数 |
| top_p | REAL | Top-P 参数 |
| top_k | INTEGER | Top-K 参数 |
| max_tokens | INTEGER | 最大Token数 |
| context_size | INTEGER | 上下文窗口大小 |
| is_enabled | INTEGER DEFAULT 1 | 启用状态 |
| is_default | INTEGER DEFAULT 0 | 是否默认模型 |
| total_tokens | INTEGER DEFAULT 0 | Token 消耗累计 |
| created_at | TIMESTAMP | 创建时间 |

### data_warehouse 表（独立数据仓库）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| result_id | INTEGER FK | 关联 watch_results.id |
| title | TEXT | 标题 |
| link | TEXT | 链接（`WHERE link != ''` 部分唯一索引去重） |
| summary | TEXT | 摘要 |
| source_name | TEXT | 来源名称（与 title 组合唯一索引 `WHERE link IS NULL OR link = ''`，防止无链接记录重复） |
| raw_data | TEXT | 原始数据（JSON） |
| is_deep_collected | INTEGER DEFAULT 0 | 是否已深度采集 |
| deep_collected_at | TIMESTAMP | 深度采集时间 |
| created_at | TIMESTAMP | 入库时间 |

### audit_logs 表（操作审计日志）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| action | TEXT NOT NULL | 操作类型 |
| username | TEXT | 操作人 |
| target | TEXT | 操作目标 |
| detail | TEXT | 详细信息 |
| client_ip | TEXT | 客户端 IP |
| created_at | TIMESTAMP | 操作时间 |

### conversations 表（对话管理）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| title | TEXT | 对话标题 |
| username | TEXT | 所属用户 |
| model_id | INTEGER FK | 使用的模型 ID，`FOREIGN KEY REFERENCES ai_models(id) ON DELETE SET NULL` |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 最后更新时间 |

### conversation_messages 表（对话消息）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| conversation_id | INTEGER FK | 所属对话（CASCADE 删除） |
| role | TEXT NOT NULL | 角色（user/assistant/system） |
| content | TEXT | 消息内容 |
| token_count | INTEGER DEFAULT 0 | Token 消耗 |
| created_at | TIMESTAMP | 创建时间 |

### digital_employees 表（数字化员工）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| name | TEXT NOT NULL | 员工名称 |
| employee_type | TEXT | 类型（llm/api） |
| description | TEXT | 能力描述 |
| model_id | INTEGER FK | 绑定模型（LLM 型），`FOREIGN KEY REFERENCES ai_models(id) ON DELETE SET NULL` |
| system_prompt | TEXT | 系统提示词（LLM 型） |
| skills | TEXT | 技能列表 JSON（LLM 型） |
| crawl4ai_enabled | INTEGER DEFAULT 0 | 启用深度采集（LLM 型） |
| api_url | TEXT | API 地址（API 型） |
| api_method | TEXT | HTTP 方法（API 型） |
| api_headers | TEXT | 请求头 JSON（API 型） |
| api_params_template | TEXT | 参数模板（API 型） |
| response_render_template | TEXT | 响应渲染模板（API 型） |
| api_secret | TEXT | API 密钥（API 型，加密存储） |
| is_enabled | INTEGER DEFAULT 1 | 启用状态 |
| created_at | TIMESTAMP | 创建时间 |
