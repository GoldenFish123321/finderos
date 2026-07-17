# 全局约束 (constraint.md)

> 本文档用于约束当前项目的全局开发规范与技术边界。请随代码变更同步更新。

## 1. 技术约束

- **语言**: Python 3.11+ (venv 中的解释器版本，推荐 3.13+)
- **Web 框架**: Tornado (`tornado.web` / `tornado.ioloop` / `tornado.httpserver`)
- **数据库**: SQLite3 (`sqlite3` 内置模块，零外部依赖)，DB 文件 `database/finderos.db`
  - **row_factory**: 使用自定义 `_dict_factory` 返回 `dict`（而非 `sqlite3.Row`），以确保 `.get()` 方法可用
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
| `app/mcp/` | MCP 协议模块（Server/Client/Tools） | 新增工具在 builtin_tools/ 添加 handler，自动发现注册 |
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
- 接口测试与 API 型员工调用: 必须执行 SSRF 校验，使用已校验 DNS 解析 IP 发起请求，不自动跟随 30x 重定向；Headers 必须是 JSON 对象且禁止 CR/LF
- API 密钥与敏感 Header: `ai_models.api_key`、`api_interfaces.api_secret`、`digital_employees.api_secret` 必须加密存储；`Authorization`、`Cookie`、`X-API-Key` 等在联动 API/表单中必须脱敏展示

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
- **默认角色**: 系统管理员(全部后台功能) / 普通用户(`/admin/model/config`，可配置模型 API)
- **后台访问**: 按功能路由做最长前缀校验，拥有任意后台功能不代表拥有全部后台功能
- **前台配置入口**: `/chat` 页面按 `/admin/model/config` 授权显示跳转链接，实际访问仍由后台路由权限校验兜底
- **默认登录落点**: 登录/注册成功后进入 `/chat`，不使用后台权限决定初始页面
- **菜单生成**: 角色 → role_functions → functions → 按 parent_id 构建树形菜单

## 7. 扩展模块 (v0.6)

### watch_sources 表（瞭源管理）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| name | TEXT NOT NULL | 瞭望源名称 |
| description | TEXT DEFAULT '' | 描述 |
| url_template | TEXT NOT NULL | URL模板（支持{keyword}/{page}占位符） |
| request_headers | TEXT DEFAULT '{}' | HTTP请求头（JSON格式） |
| parser | TEXT DEFAULT 'generic' | 响应解析器：baidu_news/sogou_news/bing_rss/generic |
| is_enabled | INTEGER DEFAULT 1 | 启用状态 |
| sort_order | INTEGER DEFAULT 0 | 排序 |
| schedule_interval | INTEGER DEFAULT 0 | 定时采集间隔（分钟，0=不启用，v0.6 迁移新增） |
| created_at | TIMESTAMP | 创建时间 |

### watch_results 表（采集结果记录）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| source_id | INTEGER FK | 瞭望源ID |
| keyword | TEXT DEFAULT '' | 采集关键词 |
| request_url | TEXT DEFAULT '' | 实际请求URL（通过 `WHERE request_url != ''` 部分唯一索引去重） |
| response_status | INTEGER DEFAULT 0 | 响应状态码 |
| response_size | INTEGER DEFAULT 0 | 响应数据大小（字节） |
| result_data | TEXT DEFAULT '' | 响应数据内容（JSON 格式存储结构化采集结果） |
| created_at | TIMESTAMP | 采集时间 |

> **注意**：本表存储每次采集的原始记录。标记保存后的结构化数据存入独立的 `data_warehouse` 表。

### ai_models 表（模型引擎）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| name | TEXT NOT NULL | 模型名称 |
| provider | TEXT DEFAULT 'openai' | 提供商（openai/deepseek/zhipu/baidu/siliconflow/moonshot/aliyun/minimax/custom） |
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
| is_default | INTEGER DEFAULT 0 | 是否默认模型（在 admin 组或单个用户 user 组内生效） |
| model_scope | TEXT DEFAULT 'admin' | 模型分组：`admin` 管理员提供模型，`user` 用户自助模型 |
| owner_username | TEXT DEFAULT '' | `user` 模型所属用户名；`admin` 模型为空 |
| total_tokens | INTEGER DEFAULT 0 | Token 消耗累计 |
| created_at | TIMESTAMP | 创建时间 |

> 分组约束：管理员模型管理页只操作 `model_scope='admin'`；普通用户快速配置页只操作 `model_scope='user' AND owner_username=<当前用户>`。聊天页合并展示当前用户自己的 user 模型与管理员提供的 admin 模型，禁止访问其他用户模型。

### data_warehouse 表（独立数据仓库）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| result_id | INTEGER DEFAULT NULL FK | 关联 watch_results.id |
| title | TEXT DEFAULT '' | 标题 |
| link | TEXT DEFAULT '' | 链接（`WHERE link != ''` 部分唯一索引去重） |
| summary | TEXT DEFAULT '' | 摘要 |
| source_name | TEXT DEFAULT '' | 来源名称（与 title 组合唯一索引 `WHERE link IS NULL OR link = ''`，防止无链接记录重复） |
| raw_data | TEXT DEFAULT '' | 原始数据（JSON） |
| is_deep_collected | INTEGER DEFAULT 0 | 是否已深度采集 |
| deep_collected_at | TIMESTAMP DEFAULT NULL | 深度采集时间 |
| created_at | TIMESTAMP | 入库时间 |

### audit_logs 表（操作审计日志）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| action | TEXT NOT NULL | 操作类型 |
| username | TEXT DEFAULT '' | 操作人 |
| target | TEXT DEFAULT '' | 操作目标 |
| detail | TEXT DEFAULT '' | 详细信息 |
| client_ip | TEXT DEFAULT '' | 客户端 IP |
| created_at | TIMESTAMP | 操作时间 |

### conversations 表（对话管理）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| title | TEXT DEFAULT '新对话' | 对话标题 |
| username | TEXT DEFAULT '' | 所属用户 |
| model_id | INTEGER FK | 使用的模型 ID，`FOREIGN KEY REFERENCES ai_models(id) ON DELETE SET NULL` |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 最后更新时间 |

### conversation_messages 表（对话消息）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| conversation_id | INTEGER FK | 所属对话（CASCADE 删除） |
| role | TEXT NOT NULL | 角色（user/assistant/tool） |
| content | TEXT DEFAULT '' | 消息内容 |
| token_count | INTEGER DEFAULT 0 | Token 消耗 |
| tool_calls | TEXT DEFAULT NULL | assistant 消息中的工具调用 JSON 数组（v1.6.1+） |
| tool_call_id | TEXT DEFAULT NULL | tool 消息对应的工具调用 ID（v1.6.1+） |
| is_sensitive | INTEGER DEFAULT 0 | 敏感内容标记（Issue #18） |
| review_status | TEXT DEFAULT 'pending' | 审核状态（Issue #18） |
| created_at | TIMESTAMP | 创建时间 |

### api_interfaces 表（接口管理，Issue #26）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| name | TEXT UNIQUE NOT NULL | 接口模板名称 |
| description | TEXT DEFAULT '' | 接口说明 |
| api_url | TEXT NOT NULL | 接口 URL 模板，支持 `{message}` |
| api_method | TEXT DEFAULT 'GET' | HTTP 方法 |
| api_headers | TEXT DEFAULT '{}' | 请求头 JSON 对象 |
| api_params_template | TEXT DEFAULT '' | 查询串或请求体参数模板 |
| response_render_template | TEXT DEFAULT '' | 数字员工响应渲染模板 |
| api_secret | TEXT DEFAULT '' | 加密存储的接口密钥 |
| is_enabled | INTEGER DEFAULT 1 | 启用状态 |
| sort_order | INTEGER DEFAULT 0 | 排序 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

### digital_employees 表（数字化员工）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| name | TEXT NOT NULL | 员工名称 |
| employee_type | TEXT NOT NULL DEFAULT 'llm' | 类型（llm/api） |
| description | TEXT DEFAULT '' | 能力描述 |
| model_id | INTEGER DEFAULT NULL FK | 绑定模型（LLM 型），`FOREIGN KEY REFERENCES ai_models(id) ON DELETE SET NULL` |
| system_prompt | TEXT DEFAULT '' | 系统提示词（LLM 型） |
| skills | TEXT DEFAULT '[]' | 技能列表 JSON（LLM 型） |
| mcp_tool_ids | TEXT DEFAULT '[]' | MCP 工具权限列表 JSON，[v0.8] 深度采集通过此字段控制 |
| crawl4ai_enabled | INTEGER DEFAULT 0 | [v0.8 废弃] 改用 mcp_tool_ids 控制 |
| api_url | TEXT DEFAULT '' | API 地址（API 型） |
| api_method | TEXT DEFAULT 'GET' | HTTP 方法（API 型） |
| api_headers | TEXT DEFAULT '{}' | 请求头 JSON（API 型） |
| api_params_template | TEXT DEFAULT '' | 参数模板（API 型） |
| response_render_template | TEXT DEFAULT '' | 响应渲染模板（API 型） |
| api_secret | TEXT DEFAULT '' | API 密钥（API 型，加密存储） |
| api_interface_id | INTEGER DEFAULT NULL FK | API 型员工来源接口模板，删除接口后置空 |
| is_enabled | INTEGER DEFAULT 1 | 启用状态 |
| created_at | TIMESTAMP | 创建时间 |
