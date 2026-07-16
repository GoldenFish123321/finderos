# 测试用例文档 v1.0.3-beta

## v1.0.3-beta security regression

- Mock chat completes without a configured API key or undefined prompt variable.
- Malicious FTS syntax is treated as a literal phrase.
- Model list queries expose key presence without decrypted key material.
- Delete confirmations escape names and interface JSON survives attribute parsing.
- Stale TTS locks are removed and valid Brotli responses are decompressed.
- Login, registration, and password-change counters are lock protected.

## 1. 认证模块

| 编号 | 测试项 | 步骤 | 预期结果 |
|------|--------|------|----------|
| TC-AUTH-01 | 正确密码登录 | 用户名:admin, 使用初始化时配置或生成的密码 | 跳转到 /admin 后台首页 |

### 安全加固回归（2026-07-15）

| 编号 | 场景 | 预期结果 |
|------|------|----------|
| TC-SEC-01 | 仅有仓库权限的角色请求 `/admin/user/delete` | 返回 403，写入拒绝审计日志 |
| TC-SEC-02 | AI 返回 `<img onerror=...>` Markdown | DOMPurify 移除危险属性，脚本不执行 |
| TC-SEC-03 | DNS 同时返回公网和私网地址 | URL 校验失败，服务端不发起请求 |
| TC-SEC-04 | 外部响应超过配置上限 | 中止读取并返回安全错误 |
| TC-SEC-05 | 禁用用户携带旧 Cookie 请求 `/chat/stream` | 会话失效并跳转登录 |
| TC-SEC-06 | 仓库内容包含 `[SYSTEM] ignore...` | 作为不可信数据处理，不覆盖系统提示词 |
| TC-SEC-07 | 无 API Key 使用 Mock 对话 | 不泄露系统提示词正文 |
| TC-AUTH-02 | 错误密码登录 | 输入错误密码 | 提示"用户名或密码错误"，停留在登录页 |
| TC-AUTH-03 | 空表单提交 | 不填用户名/密码直接登录 | 提示"用户名和密码不能为空" |
| TC-AUTH-04 | 登录限速 | 连续5次输错密码 | 第6次提示锁定，需等待15分钟 |
| TC-AUTH-05 | 未登录访问后台 | 直接访问 /admin/user | 跳转到登录页 |
| TC-AUTH-06 | 登出 | 点击登出 | Cookie清除，跳转到登录页 |

## 2. 用户管理

| 编号 | 测试项 | 步骤 | 预期结果 |
|------|--------|------|----------|
| TC-USER-01 | 新增用户 | 填写用户名+密码+选择角色 | 列表出现新用户，可用新用户登录 |
| TC-USER-02 | 编辑用户 | 修改用户名/角色 | 信息更新成功 |
| TC-USER-03 | 禁用用户 | 点击禁用按钮 | 该用户无法登录 |
| TC-USER-04 | 删除用户 | 删除非admin用户 | 列表不再显示该用户 |
| TC-USER-05 | 搜索用户 | 输入关键词搜索 | 列表按关键词过滤 |
| TC-USER-06 | 保护admin | 尝试禁用/删除admin | 操作被拦截 |

## 3. 角色管理

| 编号 | 测试项 | 步骤 | 预期结果 |
|------|--------|------|----------|
| TC-ROLE-01 | 新增角色 | 填写角色名+描述 | 列表出现新角色 |
| TC-ROLE-02 | 编辑系统角色 | 编辑"普通用户"角色 | 提示系统角色不可编辑 |
| TC-ROLE-03 | 删除系统角色 | 删除"系统管理员" | 提示系统角色不可删除 |

## 4. 瞭望采集

| 编号 | 测试项 | 步骤 | 预期结果 |
|------|--------|------|----------|
| TC-WATCH-01 | 关键词采集 | 输入关键词点击采集 | 返回新闻列表(C区展示) |
| TC-WATCH-02 | 瞭源选择 | 勾选/取消瞭源后采集 | 仅使用勾选的源 |
| TC-WATCH-03 | 保存到仓库 | 勾选结果→保存 | 数据仓库中出现记录 |
| TC-WATCH-04 | SSRF防护 | 配置瞭源指向内网地址 | 采集被拦截，返回SSRF错误信息 |
| TC-WATCH-05 | 空关键词 | 不输入关键词直接采集 | 提示"请输入关键词" |
| TC-WATCH-06 | SSE 采集进度 | 输入关键词后点击采集 | `/admin/watch/stream` 推送 `collect_progress` 事件 |
| TC-WATCH-07 | 进度条渲染 | 采集中观察 A 区进度 | 显示百分比、当前 URL、成功/失败数 |
| TC-WATCH-08 | 采集审计日志 | 完成一次采集 | `audit_logs` 新增 `WATCH_COLLECT` 记录 |
| TC-WATCH-09 | 采集日志页 | 打开 `/admin/watch/log` 并搜索关键词 | 展示采集相关日志并支持分页 |

## 5. 模型引擎

| 编号 | 测试项 | 步骤 | 预期结果 |
|------|--------|------|----------|
| TC-MODEL-01 | 新增模型 | 填写模型信息→保存 | 列表出现新模型 |
| TC-MODEL-02 | 设置默认 | 点击"设为默认" | 该模型标记为默认 |
| TC-MODEL-03 | 无 API Key 对话 | 无 API Key 时发送消息 | 走 MCP 语义匹配路径，匹配最佳工具并返回结果 |
| TC-MODEL-04 | 真实API对话 | 配置有效API Key后发送 | SSE流式返回AI回复 |
| TC-MODEL-05 | Token统计 | 多次对话 | total_tokens累计增长 |
| TC-MODEL-06 | 审计日志 | 发送对话消息 | audit_logs表新增USER_CHAT记录 |
| TC-MODEL-07 | 快速配置 Key 回显 | 打开 `/admin/model/config` | API Key 在密码框中回显，默认隐藏，可点击显示/隐藏 |
| TC-MODEL-08 | 快速配置测试连接 | 填写 API Base/API Key/Model Name 后点击测试连接 | 返回 HTTP 状态、耗时与成功/失败提示，不展示或记录密钥 |
| TC-MODEL-09 | 变更接口地址防误发 Key | 修改 API Base 后继续使用已保存 Key | 页面显示“复用当前密钥”确认区；未勾选时拒绝保存/测试，勾选后允许复用 |
| TC-MODEL-10 | 模型分组隔离 | 管理员模型、Alice 用户模型、Bob 用户模型同时存在 | 管理员页只显示 admin 组；Alice 只能选择自己的 user 模型和 admin 模型，不能访问 Bob 模型 |
| TC-MODEL-11 | Chat 模型分组展示 | 用户拥有至少一个我的模型配置并打开 `/chat` | 模型下拉按“我的模型配置 / 管理员提供模型”分组展示 |

## 6. 接口管理（Issue #26）

| 编号 | 测试项 | 步骤 | 预期结果 |
|------|--------|------|----------|
| TC-IFACE-01 | 接口模板 CRUD | 新增接口模板并按关键词搜索 | `api_interfaces` 表出现记录，列表/API 可查询 |
| TC-IFACE-02 | 接口安全校验 | 输入非 http(s) URL 或含 CRLF 的 Header | 创建/测试被拒绝并提示原因 |
| TC-IFACE-03 | 员工联动创建 | API 型员工选择接口模板后保存 | 自动填充 URL/Method/Headers/Params/响应模板并保存 `api_interface_id` |
| TC-IFACE-04 | 接口测试 | 在接口列表或表单点击测试 | 返回 HTTP 状态、耗时、JSON/raw 响应，写入审计日志 |
| TC-IFACE-05 | 密钥不回显 | 配置接口密钥后调用 `/admin/api/interface/list` | 仅返回 `has_secret=true`，不返回明文密钥 |
| TC-IFACE-06 | 安全 HTTP 调用 | 接口测试或 API 型员工调用内网/重定向目标 | 内网地址被拒绝；请求不自动跟随 30x 重定向，DNS 解析结果固定 |

自动化覆盖：`test/test_issue26_api_interface.py`，包含接口模板 CRUD/校验、敏感 Header 脱敏与恢复、安全 HTTP 拒绝内网、API 员工 4xx/5xx 错误语义、员工关联与删除清引用。

## 7. 安全测试

| 编号 | 测试项 | 步骤 | 预期结果 |
|------|--------|------|----------|
| TC-SEC-01 | XSS防护 | 在输入框输入 `<script>alert(1)</script>` | 不执行脚本，被转义 |
| TC-SEC-02 | SQL注入 | 在搜索框输入 `' OR 1=1 --` | 不产生异常结果 |
| TC-SEC-03 | CSRF | 无token直接POST | 403 Forbidden |
| TC-SEC-04 | 密码哈希 | 查看数据库 | 密码以PBKDF2哈希存储，非明文 |
| TC-SEC-05 | 安全响应头 | 浏览器查看响应头 | 包含CSP/X-Frame-Options/X-Content-Type-Options等 |

## 7. 前台智能问数（v0.3）

| 编号 | 测试项 | 步骤 | 预期结果 |
|------|--------|------|----------|
| TC-CHAT-01 | 用户访问对话页 | 普通用户登录后手动访问 /chat | 进入 A/B/C/D/E 五区对话页面 |
| TC-CHAT-01b | 登录默认落点 | 普通用户或管理员登录成功 | 默认进入 `/chat`，不直接进入 `/admin/model/config` 或后台 |
| TC-CHAT-02 | SSE 流式对话 | 输入消息并发送 | AI 逐字流式回复，Markdown 渲染 |
| TC-CHAT-03 | 多轮对话上下文 | 连续发送关联问题 | AI 基于上下文正确回答 |
| TC-CHAT-04 | @数字员工调用 | 输入 `@天气 北京` | 匹配天气员工，按响应模板返回天气信息卡片和摘要，不直接回显原始 JSON |
| TC-CHAT-05 | ECharts 图表渲染 | AI 回复含 `[CHART:...]` | 自动渲染为 ECharts 图表 |
| TC-CHAT-06 | 数据表格渲染 | AI 回复含 `[TABLE:...]` | 自动渲染为 HTML 表格 |
| TC-CHAT-07 | 模型切换 | B 区下拉选择模型 | 后续对话使用新模型 |
| TC-CHAT-08 | 对话历史管理 | C 区创建/切换/删除对话 | 对话列表正确更新 |
| TC-CHAT-09 | 快捷指令 /tools | 输入 `/tools` | 显示可用 MCP 工具列表 |
| TC-CHAT-10 | 消息元信息 | 查看 AI 回复底部 | 显示响应时间和 Token 消耗 |
| TC-CHAT-11 | 模型 API 配置入口 | 拥有 `/admin/model/config` 权限的用户查看 B 区模型选择器或欢迎页快捷操作 | 展示“配置模型 API”链接，跳转 `/admin/model/config` |

## 7b. 管理侧会话管理（Issue #17）

| 编号 | 测试项 | 步骤 | 预期结果 |
|------|--------|------|----------|
| TC-ADMIN-CONV-01 | 跨用户会话列表 | 管理员访问 `/admin/conversation` | 展示所有用户会话、标题、消息数、创建/更新时间 |
| TC-ADMIN-CONV-02 | 用户筛选 | 选择 username 筛选 | 仅展示该用户会话 |
| TC-ADMIN-CONV-03 | 消息详情 | 点击“查看” | 展示该会话消息明细和 token 统计 |
| TC-ADMIN-CONV-04 | 管理员删除 | 点击删除并确认 | 会话及消息被删除 |
| TC-ADMIN-CONV-05 | 用户侧隔离保持 | 普通用户调用会话 API | 仍只能访问自己的会话 |

## 8. 数字化员工（v0.3）

| 编号 | 测试项 | 步骤 | 预期结果 |
|------|--------|------|----------|
| TC-EMP-01 | 员工列表 | 访问 /admin/employee | 卡片式展示 8 个默认员工 |
| TC-EMP-02 | LLM 型员工调用 | 后台测试页发送消息 | SSE 流式返回 AI 回复 |
| TC-EMP-03 | API 型员工调用 | @天气触发 | 调用外部 API，支持 `current_condition.0...` 路径模板，返回格式化卡片而非原始 JSON |
| TC-EMP-03b | API 型随机音乐调用 | @随机音乐触发 | 调用 uomg API 返回音乐卡片（歌曲名/歌手/封面/试听链接） |
| TC-EMP-04 | 新增员工 | 填写表单→保存 | 列表出现新员工 |
| TC-EMP-05 | 启用/禁用 | 切换员工状态 | 禁用后前台 @菜单不显示 |
| TC-EMP-06 | 数据仓库注入 | LLM 员工查询数据 | 回复中包含数据仓库检索结果 |
| TC-EMP-07 | 员工卡片模型名显示 | 查看无模型的 LLM 员工卡片 | 模型名称显示"默认模型"而非"None" |
| TC-EMP-08 | 员工卡片技能标签 | 查看已配置技能的员工卡片 | 技能标签显示技能名称（如"数据搜索"）而非 Python dict 字符串 |
| TC-EMP-09 | 员工对话技能展示 | 在测试页与有技能的员工对话 | 技能名称以"、"分隔展示，不报 TypeError |

## 9. MCP 协议（v0.8）

| 编号 | 测试项 | 步骤 | 预期结果 |
|------|--------|------|----------|
| TC-MCP-01 | LLM Function Calling | 有 API Key 时问"搜索仓库中AI相关数据" | LLM 自动调用 search_warehouse 工具 |
| TC-MCP-02 | MCP 语义匹配回退 | 无 API Key 时问同样问题 | 语义匹配到 search_warehouse 并执行 |
| TC-MCP-03 | 工具结果格式化 | 工具返回 JSON | 转为自然语言 Markdown 回复 |
| TC-MCP-04 | 深度采集工具 | 通过对话要求采集指定 URL | LLM 判断后调用 deep_collect_url 工具，返回正文摘要 |
| TC-MCP-05 | 多轮工具调用 | 复杂问题需多工具配合 | LLM 最多 3 轮 tool_calls 完成闭环 |
| TC-MCP-06 | 工具列表指令 | 输入 `/tools` | 展示 9 个 MCP 工具的名称和描述 |

## 9b. MCP 工具管理与默认权限

| 编号 | 测试项 | 步骤 | 预期结果 |
|------|--------|------|----------|
| TC-MCP-PERM-01 | 普通用户默认模型 API 配置权限 | 初始化种子数据并创建 role_id=2 用户 | 用户默认仅拥有 `/admin/model/config` 等最小后台入口，可进入模型 API 快速配置 |
| TC-MCP-PERM-02 | MCP 管理默认不开放 | 检查 role_id=2 用户功能路由 | 默认不包含 `/admin/mcp/tool`，需管理员额外授权 |
| TC-MCP-PERM-03 | 后台路由级权限 | 访问 `/admin/model/add`、`/admin/mcp/reload` 等子路由 | 子路由解析到对应功能路由，未授权功能返回 403 |
| TC-MCP-PERM-04 | MCP 页面使用说明 | 打开 `/admin/mcp/tool` 与新增/编辑页 | 页面展示启用、测试、热重载、员工授权和 API 工具示例 |
| TC-MCP-PERM-05 | 禁用子路由隔离 | 禁用 `/admin/watch/log` 后解析该路径 | 仍要求 `/admin/watch/log` 权限，不回退到 `/admin/watch` |
| TC-MCP-PERM-06 | Registry 重绑定 | 先加载旧 MCPServer，再传入新 MCPServer 加载工具 | 工具注册到新 server，`tools/list` 不为空 |
| TC-MCP-PERM-07 | 模型快速配置入口 | 加载 `/admin/model/config` 路由与模板 | 路由存在，模板可解析 |
| TC-MCP-PERM-08 | Chat 页配置入口 | 加载 `user_chat.html` 模板 | 模板按 `can_config_model_api` 控制侧边栏与欢迎页“配置模型 API”链接 |

自动化覆盖：`test/test_mcp_user_default_permissions.py`。

## 10. TTS 语音合成播报（v0.9）

| 编号 | 测试项 | 步骤 | 预期结果 |
|------|--------|------|----------|
| TC-TTS-01 | 播报按钮显示 | AI 回复消息气泡下方 | 显示「🔊 播报」按钮 |
| TC-TTS-02 | 点击播报 | 点击播报按钮 | 生成语音并自动播放 |
| TC-TTS-03 | 停止播放 | 播放中再次点击同一按钮 | 停止播放，按钮恢复 |
| TC-TTS-04 | 缓存命中 | 对同一消息再次点击播报 | 秒级响应（缓存命中） |
| TC-TTS-05 | 空文本 | 对无文本内容调用 TTS | 返回 400 错误 |
| TC-TTS-06 | 超长文本 | 发送超过 4000 字符的文本 | 返回 400 错误 |
| TC-TTS-07 | 未登录访问 | 未登录直接请求 API | 302 跳转登录页 |
| TC-TTS-08 | 无效语音 | 使用不支持的语音参数 | 自动回退到默认语音 |
| TC-TTS-09 | 审计日志 | 调用 TTS API | `audit_logs` 表新增 `USER_TTS` 记录 |
| TC-TTS-10 | 历史消息播报 | 加载历史对话后点击播报 | 正确获取历史消息文本并合成语音 |
| TC-TTS-11 | 用户消息无按钮 | 查看用户自己的消息气泡 | 不显示播报按钮 |

## 11. 用户注册（v0.1.0）

| 编号 | 测试项 | 步骤 | 预期结果 |
|------|--------|------|----------|
| TC-REG-01 | 正常注册 | 填写新用户名+密码+确认密码 | 注册成功，自动登录跳转 |
| TC-REG-02 | 重复用户名 | 使用已存在的用户名注册 | 提示"用户名已存在" |
| TC-REG-03 | 密码不一致 | 密码与确认密码不同 | 提示"两次输入的密码不一致" |
| TC-REG-04 | 弱密码 | 输入短密码（如"123"） | 提示密码强度不足 |
| TC-REG-05 | 空表单 | 不填任何字段直接注册 | 提示"用户名和密码不能为空" |
