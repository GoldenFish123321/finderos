# API 接口文档 v0.4.0

> 基础 URL: `http://localhost:10010`
> 认证方式: Tornado Secure Cookie（登录后自动携带）
> CSRF: 所有 POST 请求需携带 `_xsrf` token

---

## 一、认证

### POST / — 用户登录
- **Content-Type**: `application/x-www-form-urlencoded`
- **参数**: `username`, `password`
- **成功**: 302 跳转（管理员→/admin，普通用户→/index）
- **失败**: 渲染登录页 + 错误提示
- **限速**: 同 IP+用户名 5次/15分钟

### POST /register — 用户注册
- **Content-Type**: `application/x-www-form-urlencoded`
- **参数**: `username`, `password`, `confirm_password`
- **成功**: 自动登录并 302 跳转（管理员→/admin，普通用户→/index）
- **失败**: 渲染注册页 + 错误提示（用户名已存在 / 密码不一致 / 密码强度不足等）

### GET /logout — 登出
- 清除 Cookie，302 跳转到 `/`

---

## 二、管理后台

> 所有 `/admin/*` 接口需要管理员权限（`AdminBaseHandler.prepare()` 校验）

### 2.1 仪表盘

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin` | 后台首页，显示统计卡片 |

### 2.2 用户管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/user` | 用户列表（?page=1&search=关键词） |
| GET | `/admin/user/add` | 新增用户表单 |
| GET | `/admin/user/edit?id=` | 编辑用户表单 |
| POST | `/admin/user/add` | 保存新用户 |
| POST | `/admin/user/edit` | 更新用户 |
| POST | `/admin/user/delete` | 删除用户 (id) |
| POST | `/admin/user/toggle` | 启用/禁用切换 (id) |

### 2.3 角色管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/role` | 角色列表 |
| GET/POST | `/admin/role/add` | 新增角色 |
| GET/POST | `/admin/role/edit` | 编辑角色 |
| POST | `/admin/role/delete` | 删除角色 (id) |

### 2.4 功能管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/function` | 功能列表（树形） |
| GET/POST | `/admin/function/add` | 新增功能 |
| GET/POST | `/admin/function/edit` | 编辑功能 |
| POST | `/admin/function/delete` | 删除功能 (id) |
| POST | `/admin/function/toggle` | 启用/禁用 (id) |

### 2.5 菜单管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/menu` | 菜单配置页（角色→功能→菜单映射） |

---

## 三、瞭望采集

### 3.1 瞭望采集主页

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/watch` | 瞭望采集页（?keyword=&page=&source_id=） |
| POST | `/admin/watch` | **执行采集** → JSON 响应 |

#### POST /admin/watch 请求参数

```json
{
  "keyword": "搜索关键词",
  "source_ids": "1,2,3"  // 瞭源ID列表，逗号分隔；为空则使用所有启用的瞭源
}
```

> **兼容格式**：同时支持 jQuery 数组语法 `source_ids[]=1&source_ids[]=2`。

#### POST /admin/watch 响应

```json
{
  "code": 0,
  "msg": "采集完成，共获取 15 条新闻",
  "news": [
    {
      "id": 1,
      "title": "新闻标题",
      "link": "https://...",
      "summary": "摘要...",
      "source_name": "百度新闻"
    }
  ],
  "results": [...],
  "total": 15
}
```

### 3.2 保存到数据仓库

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/admin/watch/save` | 保存选中结果 (result_ids) |

### 3.3 瞭源管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/watch/source` | 瞭源列表 |
| GET/POST | `/admin/watch/source/add` | 新增瞭源 |
| GET/POST | `/admin/watch/source/edit` | 编辑瞭源 |
| POST | `/admin/watch/source/delete` | 删除瞭源 |
| POST | `/admin/watch/source/toggle` | 启用/禁用瞭源 |

### 3.4 数据仓库

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/warehouse` | 数据仓库列表（?page=&search=） |
| GET | `/admin/warehouse/detail?id=` | 查看详情 |
| POST | `/admin/warehouse/delete` | 删除记录 (id) |
| POST | `/admin/warehouse/batch-delete` | 批量删除 (ids) |

---

## 四、模型引擎

### 4.1 模型管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/model` | 模型引擎列表（?page=&category=） |
| GET/POST | `/admin/model/add` | 新增模型 |
| GET/POST | `/admin/model/edit` | 编辑模型 |
| POST | `/admin/model/delete` | 删除模型 |
| POST | `/admin/model/toggle` | 启用/禁用 |
| POST | `/admin/model/default` | 设为默认模型 |

### 4.2 模型对话 (SSE) — ⚠️ 已废弃

> **v0.4.0 起已废弃**：后台模型对话功能已统一迁移至前台 `/chat/stream`（MCP 架构）。
> 请使用 [七、用户前台-智能问数](#七用户前台-智能问数v030) 中的 `/chat/stream` 端点。

### 4.3 模型 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/api/model/list` | JSON 格式模型列表（?page=&limit=&category=）。仅返回已启用模型（`is_enabled=1`） |

### 4.4 Token 消耗说明

- Token 消耗通过 `/chat/stream` 对话自动累加到 `ai_models.total_tokens`
- 数据迁移脚本 `migrate_db.py` 支持旧表 Token 数据迁移

---

## 五、已省略的补充端点

> 以下端点在前面章节中未列出，在此补充。

### 5.1 用户管理（补充）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/admin/user/batch-delete` | 批量删除用户 (ids) |
| POST | `/admin/user/batch-toggle` | 批量启用/禁用 (ids, action) |
| GET/POST | `/admin/user/change-password` | 修改密码 |

### 5.2 菜单管理（补充）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/admin/menu/sort` | 菜单排序（上移/下移） |

### 5.3 瞭望采集（补充）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/admin/watch/deep-collect` | 一站式深度采集 |

### 5.4 数据仓库（补充）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/admin/warehouse/deep-collect` | 深度采集指定仓库记录 |

---

## 六、数字化员工（v0.3.0）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/employee` | 员工列表（卡片式，?page=&type=） |
| GET | `/admin/employee/add` | 新增员工页面 |
| POST | `/admin/employee/add` | 提交新增员工 |
| GET | `/admin/employee/edit?id=` | 编辑员工页面 |
| POST | `/admin/employee/edit` | 提交编辑员工 |
| POST | `/admin/employee/delete` | 删除员工 |
| POST | `/admin/employee/toggle` | 启用/禁用员工 |
| POST | `/admin/employee/invoke` | **SSE 流式调用员工** |
| GET | `/admin/api/employee/list` | 员工 JSON API |
| GET | `/admin/employee/test` | 员工对话测试页 |

---

## 七、用户前台-智能问数（v0.3.0）

### 7.1 对话页面与流式 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/chat` | 用户前台 A/B/C/D/E 五区对话主页 |
| POST | `/chat/stream` | **SSE 流式 AI 对话**（含 MCP Function Calling） |
| POST | `/chat/employee/invoke` | **SSE 流式 @数字员工调用** |

### 7.2 前台 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/chat/models` | 获取可用模型列表（JSON） |
| GET | `/api/chat/employees` | 获取数字员工列表（JSON） |

### 7.3 对话管理 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/chat/conversation/list` | 当前用户对话历史列表 |
| POST | `/api/chat/conversation/create` | 创建新对话 |
| POST | `/api/chat/conversation/delete` | 删除对话（?id=） |
| GET | `/api/chat/conversation/messages` | 获取对话消息（?id=） |
