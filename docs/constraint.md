# 全局约束 (constraint.md)

> 本文档由 AI 自动维护，用于约束当前项目的全局开发规范与技术边界。

## 1. 技术约束

- **语言**: Python 3.11 (venv 中的解释器版本)
- **Web 框架**: Tornado (`tornado.web` / `tornado.ioloop` / `tornado.httpserver`)
- **数据库**: SQLite3 (`sqlite3` 内置模块，零外部依赖)，DB 文件 `database/finderos.db`
- **模板**: Tornado 原生模板 (`{% extends %}` / `{% block %}` / `{% module xsrf_form_html() %}`)
- **前端**: Layui 2.x + 原生 HTML + CSS + JS (未引入构建工具与前端框架)
- **虚拟环境**: `venv/`；一切依赖安装与运行必须激活 venv

## 2. 运行约束

- 入口文件: `main.py`
- 监听端口: `10010`
- 启动命令:
  ```bash
  # macOS / Linux:
  source venv/bin/activate
  # Windows:
  # venv\Scripts\activate
  python main.py
  ```
- 启动前 `init_db()` 自动创建表结构，`seed_default_data()` 插入种子数据（默认管理员账号/角色/功能），无需手动建库

## 3. 目录约束

| 目录 | 用途 | 变更规则 |
|------|------|---------|
| `app/controllers/` | Controller 层，一个业务一个文件 | 新增业务需新建文件 |
| `app/models/` | Model 层，Repository 模式 | 每个表一个文件 |
| `app/templates/` | Tornado 原生模板 | 按模块分目录 |
| `app/templates/admin/` | 管理后台模板 | 继承 `base_layout.html` |
| `app/static/` | 静态资源 (CSS/JS/图片) | 按类型分目录 |
| `docs/` | 项目文档 | 自动维护 |

## 4. 安全规范

- `set_secure_cookie`: `xsrf_cookies=True` + 模板 `{% module xsrf_form_html() %}`
- SQL 注入防护: 全部使用 `?` 参数占位符
- 密码存储: 服务端 PBKDF2-SHA256 600K 轮 + 随机盐
- 登录拦截: `login_url="/"` + `@tornado.web.authenticated`
- 管理员权限: 继承 `AdminBaseHandler`，prepare() 中校验角色为"系统管理员"
- 系统角色保护: `is_system=1` 的角色不允许编辑/删除
- 超级管理员保护: `admin` 用户不允许禁用/删除自身

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
| description | TEXT | 角色描述 |
| is_system | INTEGER DEFAULT 0 | 系统角色(1=不可删除/编辑) |
| created_at | TIMESTAMP | 创建时间 |

### functions 表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| name | TEXT NOT NULL | 功能名称 |
| icon | TEXT | Layui 图标类名 |
| route_path | TEXT | 路由地址 |
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

## 7. Day6-2 扩展模块 (v0.2)

### watch_sources 表（瞭源管理）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| name | TEXT NOT NULL | 瞭望源名称 |
| description | TEXT | 描述 |
| url_template | TEXT NOT NULL | URL模板（支持{keyword}/{page}占位符） |
| request_headers | TEXT | HTTP请求头（JSON格式） |
| is_enabled | INTEGER DEFAULT 1 | 启用状态 |
| sort_order | INTEGER DEFAULT 0 | 排序 |
| created_at | TIMESTAMP | 创建时间 |

### watch_results 表（数据仓库）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| source_id | INTEGER FK | 瞭望源ID |
| keyword | TEXT | 采集关键词 |
| request_url | TEXT | 实际请求URL |
| response_status | INTEGER | 响应状态码 |
| response_size | INTEGER | 响应数据大小（字节） |
| result_data | TEXT | 响应数据内容 |
| created_at | TIMESTAMP | 采集时间 |

### ai_models 表（模型引擎）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| name | TEXT NOT NULL | 模型名称 |
| provider | TEXT | 提供商（openai/deepseek/qwen/...） |
| api_base | TEXT | API Base URL |
| api_key | TEXT | API密钥 |
| model_name | TEXT | 模型标识 |
| category | TEXT | 分类（text/image/audio/video/multimodal/embedding） |
| system_prompt | TEXT | 系统提示词 |
| temperature | REAL | 温度参数 |
| top_p | REAL | Top-P 参数 |
| top_k | INTEGER | Top-K 参数 |
| max_tokens | INTEGER | 最大Token数 |
| context_size | INTEGER | 上下文窗口大小 |
| is_enabled | INTEGER DEFAULT 1 | 启用状态 |
| is_default | INTEGER DEFAULT 0 | 是否默认模型 |
| created_at | TIMESTAMP | 创建时间 |
