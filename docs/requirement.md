# 瞭望与问数系统 (DataFinderAgentOS) — 需求文档 v0.4.0

> 覆盖 v0.1 ~ v0.4.0 全部功能需求

---

## 一、v0.1 — 权限管理子系统

### 1. 用户管理 (`/admin/user`)

- **功能**: 列表查看、搜索、新增、删除、修改、禁用、批量删除/批量启用
- **特殊规则**: 超级管理员 `admin` 不允许禁用/删除自己
- **分页**: 20条/页
- **布局**: 三区布局 — 上(搜索+操作)、中(列表)、下(分页)

### 2. 角色管理 (`/admin/role`)

- **默认角色**: 普通用户 + 系统管理员（`is_system=1` 不可编辑/删除）
- **功能**: 新增、删除、修改，功能权限树联动（`role_functions` 中间表）

### 3. 功能管理 (`/admin/function`)

- **功能**: 新增/修改/删除/禁用（禁用级联清除角色关联）
- **层级**: 一级 + 二级（`parent_id` 自引用）

### 4. 菜单管理 (`/admin/menu`)

- **功能**: 按角色预览菜单树 + 排序（上移/下移）

### 5. 认证与安全

- PBKDF2-SHA256 60万轮密码哈希 + CSRF + XSS + SQL注入防护 + 登录限速 + 审计日志

---

## 二、v0.2 — 数据采集与 AI 引擎

### 6. 瞭望采集 (`/admin/watch`)

- 关键词采集 + 瞭源选择 + URL模板占位符（`{keyword}`/`{page}`/计算表达式）
- 内置解析器：百度新闻/搜狗新闻/通用
- SSRF 防护：协议白名单 + 内网 IP 拦截 + DNS 校验 + CRLF 检测
- 反爬策略：Cookie 预热 + Chrome TLS 指纹 + 自定义 Headers

### 7. 瞭源管理 (`/admin/watch/source`)

- CRUD + 启用/禁用 + 自定义 Request Headers + 排序

### 8. 数据仓库 (`/admin/warehouse`)

- 独立 `data_warehouse` 表（区别于 `watch_results`）
- URL 去重（`link` 唯一索引）+ 关键词搜索 + 批量删除
- 采集结果"标记保存"到仓库

### 9. 模型引擎 (`/admin/model`)

- 多 Provider（OpenAI/DeepSeek/智谱/文心/自定义）
- 6 大分类（text/image/audio/video/multimodal/embedding）
- SSE 流式对话（真实 API + Mock 回退）
- Token 消耗累计 + 对话审计日志

---

## 三、v0.3 — 前台智能问数 + 数字员工

### 10. 前台智能问数 (`/chat`)

- A/B/C/D/E 五区布局对话页面
- SSE 流式对话（Markdown 气泡渲染）
- 多轮对话持久化（`conversations` + `conversation_messages`）
- 模型切换 + 对话历史管理（创建/切换/删除）
- ECharts 图表自动注入（`[CHART:...]` / `[TABLE:...]` 标记）
- 快捷指令（`/clear` `/summary` `/trans` `/tools`）

### 11. 数字化员工 (`/admin/employee`)

- **LLM 型**：模型绑定 + system_prompt + skills + crawl4ai 可选
- **API 型**：HTTP 调用 + 参数模板 + 响应渲染模板
- 7 个默认员工（天气/采集专员/文案编写/新闻聚合/科普助手/产业专员/天机助手）
- 前台 `@` 触发自动匹配调用
- 后台测试对话页

### 12. 深度采集引擎

- 正文提取（article/main/body 标签识别）
- crawl4ai 可选增强

### 13. 定时采集调度器

- 基于 Tornado PeriodicCallback
- 按瞭望源独立配置 `schedule_interval`
- 专用线程池不阻塞 IOLoop

---

## 四、v0.4 — MCP 协议架构

### 14. MCP 协议模块 (`app/mcp/`)

- MCP Server（工具注册、MCP/OpenAI 格式互转）
- MCP Client（工具执行、语义匹配智能回退）
- 8 个标准化 MCP 工具：
  - `search_warehouse` / `get_recent_warehouse_data` / `get_warehouse_stats`
  - `deep_collect_url` / `collect_web_data`
  - `list_digital_employees` / `list_conversations` / `get_conversation_messages`

### 15. LLM Function Calling

- 有 API Key：LLM 自主决策工具调用（Tool → Execute → Reply，最多 3 轮）
- 无 API Key：MCP 语义匹配自动路由
- `/tools` 指令查看所有可用工具

### 16. FTS5 全文检索

- `data_warehouse_fts` 虚拟表 + 3 个同步触发器
- 优先 FTS5 MATCH，回退 LIKE 模糊匹配

---

## 五、数据库设计（全版本）

```
users ── roles ── role_functions ── functions (树形)
  │
  ├── conversations ── conversation_messages
  │
watch_sources ── watch_results
                   │
                   └── data_warehouse ── data_warehouse_fts

ai_models ── digital_employees

audit_logs
```

---

## 六、Bug修复历史

| 版本 | 修复项 |
|------|--------|
| v0.1 | admin 账号保护、登录跳转逻辑、角色权限分配 |
| v0.2 | SSRF 防护完善、数据仓库 URL 去重、菜单排序 |
| v0.3 | ASCII 编码错误、@数字员工卡片渲染、FTS5 搜索增强 |
| v0.4 | 废弃硬编码关键词意图识别、MCP 语义匹配替代 |
