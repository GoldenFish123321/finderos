# API 接口文档 v0.4

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

### 4.2 模型对话 (SSE)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/model/chat?model_id=` | 对话页面 |
| POST | `/admin/model/chat/stream` | **SSE 流式对话** |

#### POST /admin/model/chat/stream

**请求**: `model_id`, `message`

**SSE 事件**:
```
data: {"content": "你"}
data: {"content": "好"}
...
data: [DONE]
event: stats
data: {"tokens": 42, "mock": false}
```

- `mock: true` 表示使用本地 Mock 模式（API Key 未配置）
- Token 消耗会自动累加到 `ai_models.total_tokens`

### 4.3 模型 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/api/model/list` | JSON 格式模型列表（?page=&limit=&category=） |

---

## 五、接口管理（Issue #26）

### 5.1 接口模板管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/interface` | 接口模板列表（?page=&keyword=） |
| GET/POST | `/admin/interface/add` | 新增接口模板 |
| GET/POST | `/admin/interface/edit` | 编辑接口模板（?id=） |
| POST | `/admin/interface/delete` | 删除接口模板 (id) |
| POST | `/admin/interface/toggle` | 启用/禁用接口模板 (id) |
| POST | `/admin/interface/test` | 测试接口模板（支持 id 或表单草稿字段） |
| GET | `/admin/api/interface/list` | 获取已启用接口模板（供 API 型数字员工联动） |

### 5.2 POST /admin/interface/test

**请求参数（已保存接口）**

```json
{
  "id": 1,
  "message": "成都"
}
```

**请求参数（草稿配置）**

```json
{
  "name": "天气查询接口",
  "api_url": "https://wttr.in/{message}?format=j1",
  "api_method": "GET",
  "api_headers": "{\"Accept\":\"application/json\"}",
  "api_params_template": "",
  "response_render_template": "",
  "api_secret": "",
  "message": "成都"
}
```

**响应**

```json
{
  "code": 0,
  "msg": "测试成功",
  "status": 200,
  "elapsed_ms": 320,
  "data": {},
  "raw": "...",
  "truncated": false
}
```

安全约束：仅允许 `http/https`，执行前复用 SSRF 防护；Headers 必须是 JSON 对象且不得包含 CR/LF。接口测试不会自动跟随 30x 重定向，并使用已校验的 DNS 解析 IP 发起请求，避免 DNS Rebinding/重定向绕过。

### 5.3 数字员工联动

API 型数字员工新增/编辑页可通过 `api_interface_id` 选择接口模板。选择后前端自动填充：

- `api_url`
- `api_method`
- `api_headers`
- `api_params_template`
- `response_render_template`

接口模板中的 `api_secret` 不通过 `/admin/api/interface/list` 回显；保存员工时由服务端复用。`Authorization`、`Cookie`、`X-API-Key` 等敏感 Header 在联动 API/表单中以 `******` 脱敏展示，提交未修改的脱敏值时服务端会保留原始 Header。
