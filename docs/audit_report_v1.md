# 代码审计报告（修复加固前）

> **项目名称**：FinderOS (DataFinderAgentOS) — 智能瞭望与智能问数系统
> **审计工具**：Bandit + 自定义规则 + 人工审查
> **审计日期**：2026-07-16
> **审计版本**：v0.4（修复前）

---

## 一、审计概述

### 1.1 审计范围
对 FinderOS v0.6 版本进行全量代码安全审计，覆盖以下模块：
- 用户认证与授权（auth、RBAC）
- 前端安全（XSS、CSRF、CSP）
- 采集引擎（SSRF、输入校验）
- 模型引擎（SSRF、密钥泄露）
- 数据库操作（SQL注入）
- 会话管理（Cookie安全、会话固定）

### 1.2 审计工具
- Bandit v1.7+ — Python 静态安全分析
- 自定义检测规则（硬编码密钥、不安全反序列化等）
- 人工代码审查（前端XSS、业务逻辑漏洞）

---

## 二、漏洞清单

### CRITICAL-001：硬编码默认管理员密码
- **文件**：`app/models/db.py` → `seed_default_data()`
- **严重度**：🔴 严重
- **描述**：`seed_default_data()` 以硬编码的明文密码 `"admin888"` 创建默认管理员账户，并在控制台打印。任何获取数据库访问权限或阅读日志的攻击者都能通过已知默认凭证获取管理员权限。
- **影响**：默认凭证导致管理员账户被接管。
- **修复建议**：从环境变量 `ADMIN_DEFAULT_PASSWORD` 读取初始密码，首次登录强制修改。禁止日志输出密码。

### CRITICAL-002：API 密钥加密密钥派生可预测
- **文件**：`app/utils/security.py` → `_ensure_secret_key()` / `_get_fernet()`
- **严重度**：🔴 严重
- **描述**：Fernet 加密密钥通过 `hashlib.sha256(secret).digest()` 从 `COOKIE_SECRET` 派生。若 `COOKIE_SECRET` 未设置，应用自动生成并保存到 `.secret_key` 文件。该文件若被读取，所有已加密的 API 密钥将被破解。多实例共享镜像时可能共享相同密钥。
- **影响**：所有已加密 API 密钥批量泄露。
- **修复建议**：生产环境强制通过环境变量设置 `COOKIE_SECRET`。考虑使用 KMS 管理密钥。

### CRITICAL-003：采集器 DNS 重绑定 TOCTOU 漏洞
- **文件**：`app/services/collector.py`、`app/services/deep_collector.py`
- **严重度**：🔴 严重
- **描述**：`validate_url_safe()` 校验时解析一次 hostname 检查内网地址，但采集器将原始 URL 直接传给 `urllib.request.urlopen()` 执行第二次 DNS 解析。攻击者可在两次解析间将公开域名的 DNS 改为内网 IP（如 `127.0.0.1`），绕过 SSRF 防护访问内部服务。`user_chat.py` 中已有 `pin_url_to_ip()` 防护但未用于采集器。
- **影响**：SSRF 攻击可访问内部网络服务。
- **修复建议**：在采集器和深度采集器的所有外发请求中使用 `pin_url_to_ip()`。

### HIGH-001：Mock 聊天响应中泄露系统提示词（对应 Issue #2）
- **文件**：`app/controllers/user_chat.py` → `_mock_chat_response()`
- **严重度**：🟠 高危
- **描述**：Mock 响应直接将系统提示词内容输出给用户：`"🔧 系统提示词：{system_prompt[:100]}..."`。暴露了包含内部指令、约束和敏感上下文的系统提示词。
- **影响**：信息泄露 — 攻击者可获取系统内部指令，辅助后续 prompt injection 攻击。
- **修复建议**：删除系统提示词输出。Mock 响应使用泛型描述，如 `"🔧 系统提示词：已配置"`。

### HIGH-002：AI 模型 API Key 默认解密模式存在泄露风险
- **文件**：`app/models/ai_model.py` → `get_all()` / `get_by_id()` / `get_default()`
- **严重度**：🟠 高危
- **描述**：每个读取方法在返回前自动解密 `api_key` 字段。任何能查询模型表的代码路径都会获得明文 API Key。若 JSON API 端点不慎包含 `api_key` 字段，密钥将泄露给客户端（目前 handler 已过滤，但默认解密模式不安全）。
- **影响**：新增 API 端点可能意外泄露密钥。
- **修复建议**：采用"按需解密"模式 — 默认不填充 `api_key`，提供显式的 `get_api_key_for_model(model_id)` 方法。

### HIGH-003：管理端 Handler 绕过模板自动转义
- **文件**：`app/controllers/admin_employee.py` 等多处
- **严重度**：🟠 高危
- **描述**：管理端 handler 使用 `self.write('<script>alert("错误");window.history.back();</script>')` 直接输出内联 HTML/JavaScript，完全绕过 Tornado 模板自动转义。若未来错误消息包含用户可控数据，将产生基于 DOM 的 XSS。
- **影响**：潜在的 XSS 攻击面。
- **修复建议**：改用 `self.redirect()` 加查询参数或 `self.render()` 配合错误消息。

### HIGH-004：admin_employee.py API 型员工调用缺少 DNS 固定
- **文件**：`app/controllers/admin_employee.py` → `_invoke_api_employee()`
- **严重度**：🟠 高危
- **描述**：管理端 API 型员工调用执行了 SSRF 校验但未使用 `pin_url_to_ip()` 进行 DNS 重绑定防护。用户端（`user_chat.py`）已正确实现此防护。管理端版本易受 TOCTOU DNS 重绑定攻击。
- **影响**：通过管理端 API 员工的 SSRF 攻击。
- **修复建议**：在管理端 handler 应用与 `user_chat.py` 中 `UserEmployeeInvokeHandler` 相同的 `pin_url_to_ip()` 逻辑。

### HIGH-005：采集器在响应中暴露原始错误信息
- **文件**：`app/services/collector.py`、`app/services/deep_collector.py`
- **严重度**：🟠 高危
- **描述**：`fetch_and_parse()` 和 `deep_fetch()` 将详细异常消息返回给调用方（如 `f"Error: {e}"`），存入数据库并通过 Web UI 显示。可能暴露内部网络细节（主机名、IP、路径、库版本）。
- **影响**：信息泄露 — 辅助攻击者侦查。
- **修复建议**：记录详细错误到日志，返回通用错误消息给用户，如 `"采集失败，请稍后重试"`。

### HIGH-006：API 型员工 HTTP 头部注入风险
- **文件**：`app/controllers/user_chat.py`、`app/controllers/admin_employee.py`
- **严重度**：🟠 高危
- **描述**：用户配置的 API 头部（`api_headers` JSON）解析后直接用于外发 HTTP 请求，未进行 CRLF 检测。攻击者可通过员工创建/编辑表单注入含 `\r\n` 的头部，导致 HTTP 请求走私或 SSRF 增强。
- **影响**：HTTP 头部注入、请求走私。
- **修复建议**：对所有自定义头部的键和值应用 `has_crlf()` 检查，拒绝或清洗含 CR/LF 的头部。

### HIGH-007：Prompt Injection — 工具输出未清洗（对应 Issue #1）
- **文件**：`app/controllers/user_chat.py` → 工具调用路径
- **严重度**：🟠 高危
- **描述**：系统提示词包含 Jailbreak 防护指令，但工具输出（如数据仓库查询结果）在注入 LLM 上下文时未经过清洗。若攻击者污染数据仓库内容（如采集含 `[SYSTEM] ignore all previous instructions` 的网页），该内容作为工具结果注入时可覆盖系统指令。
- **影响**：间接 Prompt Injection — 攻击者通过数据仓库内容控制 LLM 行为。
- **修复建议**：清洗工具输出，删除类似系统提示词的模式。用 `<tool_result>...</tool_result>` 包裹工具输出。

### HIGH-008：CSP 中 `unsafe-inline` 破坏 XSS 防护
- **文件**：`app/config/settings.py` → `SECURITY_HEADERS`
- **严重度**：🟠 高危
- **描述**：CSP 同时允许脚本和样式的 `'unsafe-inline'`，几乎完全破坏 CSP 的 XSS 防护价值。任何成功的 HTML 注入都能执行内联脚本。
- **影响**：XSS 防护形同虚设。
- **修复建议**：使用 nonce 或 hash 替代 `unsafe-inline`。若 Layui 需要内联脚本，考虑重构为外部文件。

### MED-001：Cookie Secure 标志依赖协议检测
- **文件**：`app/controllers/auth.py` → 登录/注册逻辑
- **严重度**：🟡 中危
- **描述**：`secure` cookie 标志基于 `self.request.protocol == "https"` 设置。若部署在反向代理后，Tornado 只看到 `http`，导致 `secure` 标志未设置，会话 cookie 明文传输。
- **修复建议**：检查 `X-Forwarded-Proto` 头部，添加 `Strict-Transport-Security` 头部。

### MED-002：缺少 HSTS 头部
- **文件**：`app/config/settings.py` → `SECURITY_HEADERS`
- **严重度**：🟡 中危
- **描述**：`SECURITY_HEADERS` 缺少 `Strict-Transport-Security`。无 HSTS 时浏览器无法强制 HTTPS，用户易受 SSL 剥离攻击。
- **修复建议**：添加 `"Strict-Transport-Security": "max-age=31536000; includeSubDomains"`。

### MED-003：使用已弃用的 X-XSS-Protection 头部
- **文件**：`app/config/settings.py` → `SECURITY_HEADERS`
- **严重度**：🟡 中危
- **描述**：`X-XSS-Protection: 1; mode=block` 已被现代浏览器弃用，可能被滥用于绕过 CSP。
- **修复建议**：移除 `X-XSS-Protection`，完全依赖 CSP。

### MED-004：用户对话创建缺少模型验证
- **文件**：`app/controllers/user_chat.py` → `UserConversationCreateHandler`
- **严重度**：🟡 中危
- **描述**：用户创建对话时未验证指定的 `model_id` 是否存在或已启用。删除/消息端点正确检查了所有权，但创建端点存在逻辑缺口。
- **修复建议**：添加验证确保 `model_id` 对应已启用模型。

### MED-005：TTS 缓存缺少过期机制
- **文件**：`app/controllers/user_chat.py` → TTS 端点
- **严重度**：🟡 中危
- **描述**：TTS 缓存文件无过期机制，攻击者可通过请求大量独特文本填满磁盘。无基于用户的速率限制。
- **修复建议**：添加 TTS 缓存 TTL（24小时），添加用户级速率限制。

### MED-006：日志中泄露对话内容
- **文件**：`app/controllers/user_chat.py` → 多处日志记录
- **严重度**：🟡 中危
- **描述**：日志中记录包含用户消息内容（`msg_preview` 前100字符）和技能名称。若日志保护不当，对话内容可能暴露。
- **修复建议**：记录哈希/摘要而非实际内容。确保日志文件访问控制。

### MED-007：采集器 HTTP 重定向处理不一致
- **文件**：`app/services/collector.py` → `_NoRedirectHandler`
- **严重度**：🟡 中危
- **描述**：`_NoRedirectHandler` 将 3xx 响应作为正常响应返回给下游解析器，可能产生非预期行为。虽阻止了重定向（SSRF 防护），但语义不清晰。
- **修复建议**：添加注释说明设计意图，返回实际状态码。

### LOW-001：不安全的默认端口
- **文件**：`app/config/settings.py`
- **严重度**：🔵 低危
- **描述**：默认监听端口 `10010` 非标准端口。默认绑定 `127.0.0.1` 是好的。
- **修复建议**：可考虑使用更标准端口如 `8080`。

### LOW-002：Permissions-Policy 未限制剪贴板
- **文件**：`app/config/settings.py` → `SECURITY_HEADERS`
- **严重度**：🔵 低危
- **描述**：`Permissions-Policy` 未限制 `clipboard-read`、`clipboard-write`、`display-capture`。
- **修复建议**：扩展 `Permissions-Policy` 包含 `clipboard-read=(), clipboard-write=self, display-capture=()`。

### LOW-003：Brotli 解压失败回退暴露原始二进制
- **文件**：`app/services/deep_collector.py`
- **严重度**：🔵 低危
- **描述**：Brotli 解压失败时将原始二进制数据作为后备文本处理，可能导致数据库中出现乱码。
- **修复建议**：解压失败时返回错误而非传递原始数据。

### LOW-004：数据库中以明文短暂存储员工 API 密钥
- **文件**：`app/controllers/admin_employee.py`
- **严重度**：🔵 低危
- **描述**：`api_secret` 在请求处理期间以明文形式在内存中短暂存在，存储前会加密（已缓解）。
- **修复建议**：在控制器层尽早加密敏感字段。

---

## 三、风险评估

| 严重度 | 数量 | 说明 |
|--------|------|------|
| 🔴 严重 | 3 | 默认管理员密码、加密密钥可预测、DNS 重绑定 SSRF |
| 🟠 高危 | 8 | 系统提示词泄露、API Key 解密模式、XSS 防护绕过、DNS 固定缺失、错误信息泄露、HTTP 头部注入、Prompt Injection、CSP unsafe-inline |
| 🟡 中危 | 7 | Cookie Secure 标志、HSTS 缺失、X-XSS-Protection 弃用、对话验证缺失、TTS 缓存无限增长、日志泄露、重定向处理不一致 |
| 🔵 低危 | 4 | 默认端口、Permissions-Policy 不全、Brotli 回退、内存明文密钥 |
| **合计** | **22** | — |

---

## 四、审计结论

### 4.1 总体评价
FinderOS v0.6 在安全方面有较好的基础防护：PBKDF2-SHA256 密码哈希（60万次迭代）、参数化查询防 SQL 注入、XSRF Cookie 全局启用、SSRF URL 校验、Fernet 加密 API 密钥、登录频率限制等均符合 OWASP 最佳实践。

然而，本次审计发现 **22 个安全漏洞**（3 严重、8 高危、7 中危、4 低危），主要集中在以下领域：

1. **默认凭证与密钥管理**（CRITICAL-001/002）：硬编码管理员密码和可预测的加密密钥派生是最高优先级风险。
2. **SSRF 防护不完整**（CRITICAL-003、HIGH-004）：采集器和管理端 API 员工调用存在 DNS 重绑定 TOCTOU 漏洞。
3. **信息泄露**（HIGH-001/005、MED-006）：Mock 响应泄露系统提示词、错误信息暴露内部细节、日志含对话内容。
4. **LLM 安全**（HIGH-007）：工具输出未清洗，存在间接 Prompt Injection 风险。
5. **前端安全**（HIGH-003/008）：`self.write()` 绕过模板转义、CSP `unsafe-inline` 使 XSS 防护失效。

### 4.2 修复优先级

| 优先级 | 漏洞编号 | 预计工时 |
|--------|---------|---------|
| P0（立即） | CRITICAL-001 默认密码 | 0.5h |
| P1（本周） | HIGH-001 Mock 泄露、CRITICAL-003 DNS 重绑定、HIGH-004 管理端 DNS 固定 | 3h |
| P1（本周） | HIGH-003 管理端 HTML 输出、HIGH-006 头部注入 | 2h |
| P2（本月） | HIGH-008 CSP unsafe-inline、HIGH-002 API Key 解密模式 | 4h |
| P2（本月） | HIGH-007 Prompt Injection 清洗、CRITICAL-002 密钥管理 | 3h |
| P3（持续） | MED-001~007、LOW-001~004 | 5h |
