# Day6-1 权限管理子系统需求文档

> 基于 2026-07-13 人工智能产训特训 Day6 课程录制内容整理

## 任务概述

完成瞭望与问数系统 (DataFinderAgentOS) 的管理后台权限管理子系统，包含4个核心模块。

## 模块需求

### 1. 用户管理 (`/admin/user`)

- **功能**: 列表查看、搜索、新增、删除、修改、禁用
- **特殊规则**: 超级管理员 `admin` 不允许禁用/删除自己
- **分页**: 20条/页
- **布局**: 三区布局 — 上(搜索+操作)、中(列表)、下(分页)
- **字段**: 用户名、角色、状态(启用/禁用)、创建时间

### 2. 角色管理 (`/admin/role`)

- **默认角色**: 
  - 普通用户 (仅可登录前台用户侧)
  - 系统管理员 (仅可登录后台管理系统)
- **功能**: 新增、删除、修改
- **限制**: 系统管理员角色(`is_system=1`)不允许编辑/删除
- **关系**: 用户-角色 1:1
- **联动**: 角色与功能通过 Layui 树形组件联动选择（`role_functions` 中间表）
- **布局/分页**: 同用户管理

### 3. 功能管理 (`/admin/function`)

- **功能**: 新增/修改/删除/禁用
- **禁用影响**: 禁用后自动清除所有角色对该功能的关联
- **层级**: 一级 + 二级功能（通过 `parent_id` 自引用）
- **字段**: 图标(`layui-icon-*`)、名称、路由地址、父级、排序
- **布局**: 同用户管理

### 4. 菜单管理 (`/admin/menu`)

- **功能**: 按角色预览菜单结构
- **数据来源**: 角色-功能映射表（`roles → role_functions → functions`）
- **实现**: 选择角色后展示其对应的树形菜单预览 + JSON 结构

## 数据库设计

```
users ────┐ 1:1
          ↓
roles ────┐ M:N (via role_functions)
          ↓
functions (树形: parent_id 自引用)
```

## API 路由

| 路由 | 方法 | 功能 |
|------|------|------|
| `/admin` | GET | 管理后台仪表盘 |
| `/admin/user` | GET | 用户列表(支持?keyword=&page=) |
| `/admin/user/add` | GET | 新增用户表单 |
| `/admin/user/edit` | GET/POST | 编辑用户 |
| `/admin/user/delete` | POST | 删除用户 |
| `/admin/user/toggle` | POST | 启用/禁用用户 |
| `/admin/role` | GET | 角色列表 |
| `/admin/role/add` | GET | 新增角色表单(含功能树) |
| `/admin/role/edit` | GET/POST | 编辑角色(含功能树) |
| `/admin/role/delete` | POST | 删除角色 |
| `/admin/function` | GET | 功能列表 |
| `/admin/function/add` | GET | 新增功能表单 |
| `/admin/function/edit` | GET/POST | 编辑功能 |
| `/admin/function/delete` | POST | 删除功能 |
| `/admin/function/toggle` | POST | 启用/禁用功能 |
| `/admin/menu` | GET | 菜单管理(按角色预览) |

## Bug修复清单 (Day6 任务2.1-2.3)

1. ✅ **用户管理新增 useradmin 角色权限**: 系统默认只有"系统管理员"角色可访问后台，自定义角色需通过角色管理分配功能权限
2. ✅ **admin 账号保护**: admin 不可被禁用/删除
3. ✅ **登录跳转逻辑**: `set_secure_cookie` 后 `self.current_user` 不会立即反映新值，通过显式传参解决

## 默认种子数据

- 管理员账号: `admin` / `admin888`
- 系统角色: 系统管理员(id=1, 全功能权限) / 普通用户(id=2, 无后台权限)
- 默认功能: 控制台、权限管理(含4子功能)、系统设置
