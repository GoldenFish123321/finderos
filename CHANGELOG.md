# CHANGELOG

## [1.10.1-beta] — 2026-07-17

### 修复

- **数据仓库 `datatype mismatch` 错误修复**
  - 修复 LLM 调用 `get_recent_warehouse_data` 时传入 `limit: null` 导致 SQLite `IntegrityError: datatype mismatch` 的问题
  - 新增 `_sanitize_limit()` 辅助函数，统一规范化所有数据仓库查询的 `limit` 参数（处理 None / 负数 / 字符串 / float('inf') 等边界情况）
  - 为 `get_recent`、`search`、`get_source_distribution`、`get_dashboard_source_geo`、`get_keyword_frequency`、`get_recent_dashboard_items` 和 `_search_warehouse_fulltext` 添加参数清理
  - 修复 `mcp_tools` 表中 `get_recent_warehouse_data`、`search_warehouse`、`get_warehouse_stats` 的 `input_schema` 为空的问题，补全参数类型和默认值定义，帮助 LLM 正确传参
  - 修复 `registry.py` 中参数映射时 `None` 值直接透传的问题，改为回退到 schema 默认值
  - 修复 `user_chat.py` 中工具调用失败时错误被静默吞掉的问题，现在会向用户显示具体错误信息

## [1.10.0-beta] — 2026-07-17

### 新功能

- **补全三个可配置瞭望采集源**
  - 默认启用百度新闻、搜狗搜索和 Bing RSS，并在已有数据库中幂等补齐缺失来源
  - 为瞭望源增加显式解析器配置，页面采集、MCP 采集和定时采集统一遵循该配置
  - 新增 Bing RSS 结构化 XML 解析器及 DTD/ENTITY、响应大小和字段长度防护
  - 管理页面支持查看和编辑解析器、定时采集间隔
  - 补充数据库迁移、三源采集落库、解析器路由及安全边界测试

### 修复

- **切换历史对话不渲染图表**
  - `loadConversation` 加载历史消息时补充调用 `detectAndRenderChart`，确保 `[CHART:...]` / `[TABLE:...]` 标记正确渲染为 ECharts 图表和 HTML 表格
  - 修复多条 AI 消息含图表时的 Chart ID 冲突（`chartIndex` 改为模块级全局计数器）
  - 修复切换对话时未清理旧图表造成的 ECharts 实例和 ResizeObserver 内存泄漏（新增 `_cleanupChartContainers` 辅助函数）
- **脚本编写指南移至正确位置**
  - 将"脚本编写指南"从系统设置页（`/admin/config`）移至 MCP 工具编辑页（`/admin/mcp/tool/edit`）的脚本工具配置区
  - 指南仅在 `tool_type=script` 时显示，与脚本编辑上下文一致

## [1.9.9-beta] — 2026-07-17

### 修复

- **手势摄像头不再遮挡操作说明** (#158)
  - 将视频、骨架画布和识别状态限制在独立预览层内，说明区域保持在预览层外
  - 预览同时受 `640px` 和视口高度约束，低高度桌面不再与固定输入栏重叠
  - 补充摄像头分层结构和低高度布局回归测试
- **统一账户密码策略** (#160)
  - 注册、管理员新增或重置、后台自助修改、账户设置及管理员 CLI 统一要求至少 8 位且包含至少两类字符
  - 后端所有用户入口统一执行共享密码强度校验，前端提示和最小长度同步
  - 补充弱密码拒绝、合规密码修改及新密码登录验证

## [1.9.8-beta] — 2026-07-17

### 重构

- **提取硬编码 AI prompt 到 docs/prompts/ 文件** (PR #157, commit f5325ad)
  - 24 个 AI prompt（4 system + 6 employee + 14 skill）从 Python 代码中提取到 docs/prompts/ 目录
  - 新增 `docs/prompts/employees/` 和 `docs/prompts/skills/` 子目录分类管理
  - `user_chat.py`: 4 个 system prompt 常量改为 `_load_prompt()` 从文件加载
  - `db.py`: 6 个员工 + 14 个技能 prompt 改为 `_load_prompt_file()` 加载
  - 文件缺失时抛出明确的 `RuntimeError`，包含完整路径，避免静默失败
  - 新增 `app/templates/admin/403.html` 统一 403 错误页面，消除 3 处重复内联 HTML
  - 新增 `TestPromptFileLoading` 测试类（6 个测试），验证文件完整性和加载一致性
  - 新增 `docs/prompts/README.md`，说明目录结构和修改方法

### 改进

- 非开发人员可直接编辑 .txt 文件修改 prompt，无需触碰 Python 代码
- 403 错误页面统一为 Tornado 模板，支持动态 message/link/link_text 参数
