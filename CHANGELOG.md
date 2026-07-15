# Changelog

## v1.0.3-beta (2026-07-16) - Security issue hardening

- Fixed Issues #57-#76 covering Mock runtime errors, URL/FTS injection, DOM XSS,
  rate-limit races, stale TTS locks, response secret exposure, and Brotli handling.
- AI model reads no longer decrypt API keys unless explicitly required.
- Random administrator bootstrap passwords are no longer written to process logs.
- Added focused regression tests for the new trust-boundary and concurrency fixes.

本文档记录瞭望与问数系统 (DataFinderAgentOS) 所有版本的变更历史。

---

## v1.0.2-beta (2026-07-15) — 安全加固与种子数据完善

- 🔒 **安全修复 #1 [CRITICAL]**：数据仓库内容拼入 system prompt 前进行 Prompt Injection 脱敏（XML 标签包裹 + 高危模式过滤 + 长度截断）(@GoldenFish123321)
- 🔒 **安全修复 #2 [HIGH]**：Mock 回复中移除 system prompt 内容泄露，仅保留配置状态 (@GoldenFish123321)
- 🗄️ **种子数据 #41**：为全部 LLM 型员工配置 mcp_tool_ids，基于名称解析消除 ID 漂移风险 (@GoldenFish123321)
- 🗄️ **种子数据 #42**：消除硬编码数字 MCP 工具 ID，全部改为名称→ID dict 查找 (@GoldenFish123321)
- 🗄️ **种子数据 #43**：5 个默认技能补充 mcp_tool_id 绑定对应 MCP 工具 (@GoldenFish123321)
- 🗄️ **种子数据 #44**：种子技能从 5 个扩展到 14 个，涵盖产业分析/政策解读/文案撰写等 (@GoldenFish123321)
- 🗄️ **种子数据 #45**：MCP 工具描述统一升级为富描述版本（含 prompt engineering hints） (@GoldenFish123321)
- 🔄 **迁移修复 #46**：migrate_db.py 新增 crawl4ai_enabled → mcp_tool_ids 迁移步骤 (@GoldenFish123321)
- 🧪 **测试新增**：24 个安全测试用例 + 种子数据一致性验证测试

---

## v1.0.1-beta (2026-07-15) — MCP Fallback 工具补齐

- 🐛 **修复 #47**：`ALL_TOOL_DEFINITIONS` fallback 路径缺失 8 个工具定义，现已补齐为 18 个（与 `builtin_tools/` 导出完全一致）
- 🧪 **测试增强**：新增 `TestAllToolDefinitions` 测试类，验证 18 个工具完整性、handler 可调用性、schema 规范性（3 项测试）

---

## v1.0.0-beta (2026-07-15) — 版本号统一

- 📌 **版本号体系修正**：统一代码、文档、模板中所有版本引用，建立清晰的语义化版本体系
- 📋 **独立 Changelog**：将更新日志从 README 中分离为独立的 `CHANGELOG.md`
- 🔐 **安全加固**：按路由执行后台 RBAC；禁用用户旧会话失效；AI Markdown 经 DOMPurify 净化；服务端外呼统一 DNS 固定、禁重定向和响应上限
- 🧠 **LLM 信任边界**：修复 Issue #1 间接 Prompt Injection 与 Issue #2 Mock 系统提示词泄露
- 🧰 **MCP 种子一致性**：修复 Issue #41-#50，员工/Skill 按名称绑定工具，补齐 fresh-install 能力，迁移 Crawl4ai 权限并自动发现 builtin handler

---

## v0.10 (2026-07-15) — MCP 重构完成

- 🔧 **MCP 工具种子数据**：18 个内置工具迁移至数据库驱动，含完整 description 和 input_schema
- 🏷️ **三色徽章系统**：员工卡片区分 MCP 工具（蓝色 `.mcp-tag`）、Skill（绿色 `.skill-tag`）、旧 TAG（橙黄 `.legacy-tag`）
- 🗑️ **crawl4ai_enabled 废弃**：改为通过 MCP 工具 `collect_with_crawl4ai` / `batch_deep_collect` 控制
- 🔗 **Skill 绑定 MCP 工具**：技能表单新增 MCP 工具下拉选择器，`mcp_tool_id` 关联
- 🔄 **旧 TAG 迁移**：`migrate_legacy_tags_to_skills_v042` 将员工旧格式字符串标签转换为 Skill ID 数组
- 🔐 **SSRF 防护增强**：crawl4ai 工具新增 `validate_url_safe` URL 安全校验
- 📋 **员工前端增强**：`UserEmployeeListHandler` API 返回三色徽章数据
- 🧪 **测试覆盖**：6 项测试全部通过（工具查询/CRUD/注册表/员工权限/技能关联/测试日志）

### Bug 修复：sqlite3.Row .get() AttributeError

- 🐛 **修复 `list_watch_sources` 工具崩溃**：`sqlite3.Row` 对象不支持 `.get()` 方法，导致 `AttributeError`
- 🔧 **根因修复**：将 `db.py` 的 `row_factory` 从 `sqlite3.Row` 改为自定义 `_dict_factory`，所有数据库查询统一返回 `dict`
- 📝 **影响范围**：全局修复了所有潜在的 `.get()` 调用兼容性问题
- 🔄 **PRAGMA 兼容**：5 处 `row[1]` 迁移检查改为 `row["name"]` 键访问
- 🧹 **注释清理**：移除 `admin_warehouse.py` 中过时的 `sqlite3.Row 不支持 .get()` 注释
- 🧪 **测试补充**：新增 `test/test_dict_factory.py` 验证 dict 返回类型与 `.get()` 支持
- 📄 **文档更新**：`constraint.md` 增加 row_factory 约束说明

## v0.9 (2026-07) — 管理侧接口管理（Issue #26）

- 🔗 **接口管理模块**：新增 `/admin/interface` 接口模板 CRUD、启用/禁用、列表搜索与接口测试。
- 🧩 **数字员工联动**：API 型员工表单可选择接口模板，自动填充 URL / Method / Headers / Params / Response Template。
- 🔐 **密钥安全**：接口密钥加密入库，联动创建员工时服务端复用；敏感 Header 脱敏展示并支持安全恢复。
- 🛡️ **安全 HTTP 调用**：接口测试与 API 型员工调用共用安全 HTTP 工具，拒绝内网地址、固定已校验 DNS 解析结果、禁止自动重定向并校验 Header/Host。
- 🧪 **测试补充**：新增 `test/test_issue26_api_interface.py` 覆盖接口模板、校验、安全调用和员工关联。

### UI 显示修复

- 🐛 **修复员工卡片模型名称显示 "None"**：`model_name` 为 `None` 时模板默认值回退不生效，改用 `or` 运算符确保正确显示"默认模型"
- 🐛 **修复员工卡片技能标签显示为 dict 字符串**：技能 ID 解析后返回 dict 列表但模板直接渲染为 Python 字面量，改为提取 `name` 字段作为字符串列表
- 🐛 **修复员工对话中技能名称 join 异常**：`skills_list` 为 int ID 数组时 `"、".join()` 会抛出 TypeError，增加 ID→名称解析逻辑

### TTS 语音合成播报

- 🔊 **Edge TTS 语音播报**：AI 回复消息一键朗读，使用 Microsoft Edge 免费 TTS 服务
- 🎙️ **6 种中文语音**：晓晓/云希/云健/晓伊/云扬/晓晨，默认「晓晓」神经网络语音
- 💾 **智能缓存**：基于文本 MD5 的本地缓存，相同文本不重复生成
- ⏯️ **播放控制**：点击播报开始播放，再次点击停止；支持暂停/恢复
- 🔒 **安全审计**：TTS 调用写入 `audit_logs` 表（`USER_TTS`）
- 🎨 **前端交互**：气泡下方显示 🔊 播报按钮，加载动画 + 播放状态指示

## v0.8 (2026-07) — MCP 协议架构重构

- 🔌 **MCP 协议模块**：新增 `app/mcp/` 完整实现（Server / Client / Tools）
- 🔧 **9 个 MCP 工具**：search_warehouse / get_recent_warehouse_data / get_warehouse_stats / deep_collect_url / collect_web_data / list_digital_employees / get_random_music / list_conversations / get_conversation_messages
- 🤖 **LLM Function Calling**：有 API Key 时 LLM 自主决策工具调用（Tool → Execute → Reply 闭环，最多 3 轮）
- 🧠 **MCP 语义匹配**：无 API Key 时基于工具描述的多维语义评分自动路由，替代旧关键词硬匹配
- 🗑️ **废弃旧代码**：移除 `_detect_intent_and_query` 及 50+ 硬编码关键词意图识别逻辑
- 🆕 **/tools 指令**：输入 `/tools` 查看所有可用 MCP 工具列表
- 📝 **工具结果格式化**：`_format_tool_result_as_reply` 将工具 JSON 转为自然语言 Markdown 回复

## v0.7 (2026-07) — 技能管理模块

- 🎯 **技能管理模块**：新增 `/admin/skill` 技能库 CRUD，支持 Prompt 模板管理
- 🔗 **技能绑定 MCP 工具**：Skill 可关联 MCP 工具，LLM 按需加载
- 📝 **纯 Prompt 模板**：统一 Skill 模型，移除 prompt/function 类型区分

## v0.6 (2026-07) — Crawl4ai 深度采集 + 定时调度

- 🕷️ **Crawl4ai 深度采集增强**：可选+回退机制，正文提取优化
- ⏰ **定时采集调度器**：基于 Tornado PeriodicCallback 的自动采集
- 📊 **watch_sources.schedule_interval**：瞭望源定时采集间隔配置

## v0.5 (2026-07) — 多轮对话支持

- 💬 **多轮对话**：新增 `conversations` + `conversation_messages` 双表持久化
- 📜 **对话历史侧边栏**：历史消息保存/切换/删除
- 🔍 **FTS5 全文检索**：`data_warehouse_fts` 虚拟表 + 同步触发器

## v0.4 (2026-07) — 数字化员工

- 🧑‍💼 **数字化员工模块**：LLM 型 + API 型，种子数据（产业专员/天机助手等）
- 🔑 **API Key 加密存储**：Fernet 对称加密保护敏感密钥
- 🌐 **API 型员工**：HTTP 调用 + 参数模板 + 响应渲染模板

## v0.3 (2026-07) — 前台智能问数系统

- ✅ **前台智能问数**：A/B/C/D/E 五区布局对话页面（`/chat`）
- ✅ **SSE 流式对话**：真实 API + Mock 回退，Markdown 气泡渲染
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

## v0.2 (2026-07) — 数据采集与 AI 引擎

### 数据仓库独立化
- ✅ 新增独立 `data_warehouse` 表（标题/链接/摘要/来源 + URL 去重索引）
- ✅ `DataWarehouseRepository` 仓储层实现
- ✅ 仓库详情页使用字典访问替代 `sqlite3.Row.get()` 方法

### 菜单排序与审计增强
- ✅ 菜单排序功能（上移/下移，修改 `sort_order`）
- ✅ 审计日志表索引优化（`action` / `username` / `created_at`）

### 安全与统计增强
- ✅ `ai_models.total_tokens` 列（Token 消耗累加统计）
- ✅ `audit_logs` 审计日志表（含 3 个索引）
- ✅ 登录/登出/锁定/对话等关键操作审计记录

### Day6-2 扩展模块
- ✅ **瞭望采集引擎**：百度新闻/搜狗新闻/通用解析器，URL 模板占位符，Cookie 预热反爬
- ✅ **瞭望源管理**：CRUD + 启用/禁用，自定义 Request Headers
- ✅ **数据仓库**：采集结果统一存储、关键词检索、批量管理
- ✅ **AI 模型引擎**：多 Provider（OpenAI/DeepSeek/智谱/文心/自定义），6 大分类
- ✅ **SSE 流式对话**：真实 API + 本地 Mock 回退，Token 消耗追踪
- ✅ **SSRF 防护**：协议白名单 + 内网 IP 段拦截 + DNS 解析校验 + CRLF 检测
- ✅ **安全响应头**：OWASP 推荐全量响应头（CSP/X-Frame/HSTS 等）
- ✅ **模型 JSON API**：`GET /admin/api/model/list` 供外部调用

## v0.1 (2026-07) — 基础框架

- ✅ **权限管理子系统**：用户/角色/功能/菜单完整 CRUD
- ✅ **RBAC 权限模型**：用户→角色→功能，两级树形功能结构
- ✅ **登录认证**：PBKDF2-SHA256 60 万轮 + 登录频率限速
- ✅ **管理后台**：Layui 2.x UI，三区布局（搜索+表格+分页）
- ✅ **系统保护**：admin 账号保护、系统角色保护（is_system）、功能禁用级联
- ✅ **安全基础**：CSRF 防护、SQL 注入防护、XSS 防护
- ✅ **种子数据**：自动建表 + 默认角色/管理员/功能菜单
