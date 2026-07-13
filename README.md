# 瞭望与问数系统 (DataFinderAgentOS) v0.1

基于 Tornado 异步 Web 框架构建的轻量级数据查询与分析平台。

## 技术栈

- **语言**: Python 3.11
- **Web 框架**: Tornado
- **数据库**: SQLite3
- **前端**: Layui 2.x + 原生 HTML/CSS/JS
- **安全**: 服务端 PBKDF2-SHA256 + 随机盐 + XSRF 防护 + Secure Cookie

## 项目结构

```
DataFinderAgentOS/
├── .gitignore                # Git 忽略规则
├── main.py                   # 程序入口
├── requirements.txt          # Python 依赖
├── app/
│   ├── config/               # 配置模块
│   │   ├── __init__.py
│   │   └── settings.py       # 全局配置（支持环境变量覆盖）
│   ├── controllers/          # 控制器层
│   │   ├── __init__.py
│   │   ├── auth.py           # 登录/登出处理器
│   │   ├── base.py           # 公共基础 Handler（认证）
│   │   ├── home.py           # 前台主页处理器
│   │   ├── admin_base.py     # 管理后台基础 Handler（权限校验）
│   │   ├── admin_home.py     # 管理后台主页/控制台
│   │   ├── admin_user.py     # 用户管理 CRUD
│   │   ├── admin_role.py     # 角色管理 CRUD
│   │   ├── admin_function.py # 功能管理 CRUD（树形结构）
│   │   └── admin_menu.py     # 菜单管理
│   ├── models/               # 数据模型层
│   │   ├── __init__.py
│   │   ├── db.py             # 数据库连接与初始化
│   │   ├── user.py           # 用户仓储（Repository 模式）
│   │   ├── role.py           # 角色仓储
│   │   └── function.py       # 功能仓储
│   ├── templates/            # Tornado 模板
│   │   ├── base.html         # 基础模板
│   │   ├── login.html        # 登录页
│   │   └── admin/            # 后台模板
│   │       ├── base_layout.html   # 后台布局模板
│   │       ├── index.html         # 管理后台主页（控制台）
│   │       ├── user_list.html     # 用户列表
│   │       ├── user_form.html     # 用户新增/编辑表单
│   │       ├── role_list.html     # 角色列表
│   │       ├── role_form.html     # 角色新增/编辑表单
│   │       ├── function_list.html # 功能列表
│   │       ├── function_form.html # 功能新增/编辑表单
│   │       └── menu.html          # 菜单管理
│   └── static/               # 静态资源
│       ├── css/base.css
│       └── js/base.js
├── database/                 # SQLite 数据库文件目录
└── docs/
    └── constraint.md         # 开发规范文档
```

## 快速开始

### 1. 创建虚拟环境并安装依赖

```bash
python -m venv venv

# Windows
venv\Scripts\activate
pip install -r requirements.txt

# Linux/macOS
source venv/bin/activate
pip install -r requirements.txt
```

### 2. 启动服务

```bash
# Windows
venv\Scripts\activate
python main.py

# Linux/macOS
source venv/bin/activate
python main.py
```

### 3. 访问系统

浏览器打开 http://localhost:10010/

- 首次启动会自动创建 SQLite 数据库和所有表结构
- 种子数据自动创建默认管理员账号：
  - 用户名：`admin`
  - 密码：`admin888`

## 功能特性

- ✅ 用户登录/登出（PBKDF2-SHA256 密码哈希 + 随机盐）
- ✅ 基于 Secure Cookie 的会话管理
- ✅ XSRF 跨站请求伪造防护
- ✅ SQL 参数化查询防注入
- ✅ 已登录用户自动跳转后台
- ✅ 未登录访问拦截（自动重定向到登录页）
- ✅ Layui 后台管理框架
- ✅ Repository 模式数据访问层

## 安全说明

本项目为原型框架版本，生产环境部署前需：

1. 定期备份 `database/finderos.db`
