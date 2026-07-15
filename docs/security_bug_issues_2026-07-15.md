# DataFinderAgentOS Bug 与安全漏洞 Issue 清单

## 2026-07-16 follow-up (#57-#76)

Version `1.0.3-beta` closes the fourth-round review findings: unsafe URL and
FTS interpolation, DOM confirmation XSS, unbounded registration attempts,
race-prone in-memory counters, stale TTS locks, unnecessary API-key
decryption, raw third-party secret display, and inconsistent Brotli handling.
Dedicated regression coverage lives in `test/test_issues_57_76.py`.

审计日期：2026-07-15  
审计版本：v0.4.0 (`8ffd488`)  
审计方式：静态代码审计、敏感模式检索、现有测试执行。当前环境未提供 MonkeyScan，因此未使用该工具。  
范围：`main.py`、`app/`、`test/`、配置与数据库初始化逻辑。

> 修复状态（2026-07-15）：SEC-001 至 SEC-007、BUG-001、BUG-002 均已处理。
> GitHub Issue #1、#2 同步修复。自动化回归结果为 220 passed、6 skipped；
> 另已完成真实服务登录、聊天、细粒度 RBAC 和禁用会话失效的端到端手测。

## 汇总

| ID | 严重性 | 类型 | 标题 |
|---|---|---|---|
| SEC-001 | 严重 | 越权 | 后台 RBAC 只校验“任意功能”，可跨模块访问全部管理接口 |
| SEC-002 | 高 | XSS | AI Markdown 未净化即写入 `innerHTML` |
| SEC-003 | 高 | SSRF | 多条服务端外呼链路未完整执行 IP 固定与重定向校验 |
| SEC-004 | 高 | 身份认证 | 禁用普通用户后既有会话仍可继续调用前台 API |
| SEC-005 | 中 | XSS | 数字员工测试页和技能编辑器直接拼接 HTML |
| SEC-006 | 中 | 凭证安全 | 首次启动固定创建弱口令管理员且不强制修改 |
| SEC-007 | 中 | DoS | 外部 HTTP 响应无大小上限，可耗尽内存和线程池 |
| BUG-001 | 中 | 测试/回归 | v0.4 实现与回归测试不同步，测试基线不可用 |
| BUG-002 | 低 | 并发 | 登录限速器共享字典无同步保护 |

---

## SEC-001：后台 RBAC 可跨模块越权

**严重性：严重（建议 P0）**  
**CWE：CWE-862 Missing Authorization**

### 证据

- `app/controllers/admin_base.py:64-82` 只判断当前角色是否关联了至少一个功能。
- 所有 `/admin/*` Handler 都继承 `AdminBaseHandler`，但没有将 `request.path` 与用户获授功能的 `route_path` 对应校验。
- 因此，一个只获授“数据仓库查看”等低权限功能的角色，也可直接请求 `/admin/user/add`、`/admin/role/edit`、`/admin/model/edit` 等接口。

### 影响

低权限后台账号可以管理用户、角色、模型密钥、瞭望源和数字员工，最终可提升权限、读取或替换敏感配置，并组合 SSRF 问题访问内网。

### 复现

1. 创建仅关联一个非敏感功能的角色并分配给测试用户。
2. 以该用户登录。
3. 直接请求 `POST /admin/user/add` 或 `POST /admin/role/edit`，携带合法 XSRF Token。
4. 当前代码不会进行目标功能授权检查。

### 修复建议

- 为每个 Handler 声明明确的权限标识，例如 `required_permission = "user.manage"`。
- 在 `AdminBaseHandler.prepare()` 中校验该权限，而不是仅检查功能列表非空。
- 将页面、读取、创建、修改、删除权限分开；所有 JSON/API 和批量接口同样校验。
- 添加“仅有 A 权限不能调用 B 模块接口”的集成测试。

---

## SEC-002：AI Markdown 渲染导致 XSS

**严重性：高（建议 P0）**  
**CWE：CWE-79 Improper Neutralization of Input During Web Page Generation**

### 证据

- `app/templates/user_chat.html:980` 将流式模型输出经 `marked.parse()` 后直接赋给 `innerHTML`。
- `app/templates/user_chat.html:1056` 对历史消息执行同样操作。
- 页面未引入 DOMPurify 等 HTML 净化器；Marked 配置也没有禁用原始 HTML。
- 助手回复会写入 `conversation_messages`，重新加载历史时再次渲染，形成持久化 XSS。

### 影响

恶意模型、被污染的数据仓库内容或 Prompt Injection 可返回带事件处理器、危险链接等 HTML，在用户会话中执行脚本，窃取页面数据并代用户发起同源管理操作。

### 修复建议

- 使用 DOMPurify 对 `marked.parse()` 的结果做严格净化后再写入 DOM。
- 禁止原始 HTML，并限制链接协议为 `http`、`https`、`mailto`。
- 用户消息应使用 `textContent`；不要让用户输入经过 Markdown HTML 渲染。
- 为 `<img onerror>`, `<svg onload>`, `javascript:` 链接添加回归用例。

---

## SEC-003：SSRF 防护在不同外呼链路中不一致

**严重性：高（建议 P0）**  
**CWE：CWE-918 Server-Side Request Forgery**

### 证据

- `validate_url_safe()` 只解析一个 IPv4 地址；调用方必须使用返回 IP 发起请求。
- `app/controllers/admin_employee.py:629-652` 校验 URL 后仍对原域名调用 `urlopen()`，并允许默认重定向，存在 DNS 重绑定和跳转到内网的窗口。
- `app/controllers/user_chat.py:246-260` 的模型 API 调用完全未做 SSRF 校验，且携带模型 API Key。
- `app/controllers/user_chat.py:1314-1343` 虽固定首个 IP，但仍使用默认重定向处理器；重定向目标不会重新校验，Authorization 也可能被带往非预期主机。
- `socket.gethostbyname()` 只验证单个 IPv4 结果，没有检查全部 A/AAAA 地址。

### 影响

攻击者可借服务端访问回环、内网服务或云元数据端点；模型/员工凭证还可能经恶意重定向泄露。SEC-001 会显著降低配置恶意外呼 URL 的门槛。

### 修复建议

- 建立唯一的安全 HTTP 客户端，所有 collector、模型和员工外呼统一使用。
- 解析并验证全部 A/AAAA 地址，拒绝任一私网、保留、链路本地或非全局地址。
- 禁止自动重定向；如业务需要，逐跳重新解析、重新校验并限制跳转次数。
- 跨主机跳转必须移除 `Authorization`、Cookie 和自定义敏感头。
- HTTPS 不能简单把 hostname 替换成 IP，否则证书/SNI 校验可能失效；应通过受控连接层固定目标 IP，同时保留原始 SNI 和主机名验证。

---

## SEC-004：禁用用户后前台会话不失效

**严重性：高（建议 P1）**  
**CWE：CWE-613 Insufficient Session Expiration**

### 证据

- `BaseHandler.get_current_user()` 只验证安全 Cookie 签名，不查询用户是否存在或启用。
- `AdminBaseHandler.prepare()` 会检查禁用状态，但 `/chat`、`/chat/stream`、`/chat/employee/invoke` 与 `/api/chat/*` 仅使用 `@authenticated`。

### 影响

管理员禁用或删除普通用户后，只要其签名 Cookie 尚有效，该用户仍可访问聊天、调用模型、数字员工和 MCP 工具，产生费用或继续读取数据。

### 修复建议

- 在统一的 `prepare()` 或 `get_current_user()` 会话验证层检查用户存在性及 `is_enabled`。
- Cookie 中加入会话版本；密码修改、禁用、删除时递增版本以撤销全部现有会话。
- 为禁用后的所有前台页面和 API 增加 401/403 测试。

---

## SEC-005：后台数字员工页面存在 DOM XSS

**严重性：中（建议 P1）**

### 证据

- `app/templates/admin/employee_test.html:101` 将用户输入和 SSE 内容拼入 `innerHTML`。
- `app/templates/admin/employee_form.html:205` 将技能名称直接拼入 `innerHTML`。
- 员工 API 的响应或管理员输入的技能名可以包含 HTML。

### 修复建议

使用 `textContent` 和 DOM 节点构建气泡、标签与删除按钮；如果确需 Markdown，复用 SEC-002 的统一净化器。

---

## SEC-006：默认管理员使用公开固定弱口令

**严重性：中（公网部署时为严重，建议 P1）**  
**CWE：CWE-1392 Use of Default Credentials**

### 证据

- `app/models/db.py:334-339` 首次初始化固定创建 `admin/admin888`。
- 系统不强制首次登录修改密码；README 公开该凭证。
- 配置允许通过 `BIND_ADDRESS=0.0.0.0` 暴露服务。

### 修复建议

- 首次启动要求通过环境变量或交互流程提供强随机密码。
- 未设置管理员凭证时不创建可登录管理员，或生成一次性密码并要求首次登录修改。
- 增加 `must_change_password` 状态并阻止未改密账户访问其他功能。

---

## SEC-007：外部响应无大小限制导致资源耗尽

**严重性：中（建议 P1）**  
**CWE：CWE-400 Uncontrolled Resource Consumption**

### 证据

- `collector.py`、`deep_collector.py`、`admin_employee.py` 和 `user_chat.py` 多处直接调用 `resp.read()`。
- 未检查 `Content-Length`，也没有分块读取上限；解压后的内容同样缺少大小限制。
- LLM 请求超时最长 120 秒，固定线程池可被慢响应占满。

### 影响

恶意或异常上游可返回超大/压缩炸弹响应，导致进程内存耗尽；慢连接可长期占用工作线程，阻塞其他用户。

### 修复建议

- 设置原始响应和解压后响应上限，例如 10 MiB/30 MiB，分块读取并超限中止。
- 限制并发、连接超时、首字节超时和总耗时。
- 对用户级模型/员工调用增加频率及并发配额。

---

## BUG-001：测试基线与 v0.4 实现不同步

**严重性：中（建议 P1）**

### 证据

执行 `python -m unittest discover -s test -v`：共 62 项，5 失败、32 报错。

主要问题：

- `test_v0_3_enhancements.py` 仍调用 v0.4 已删除的 `_detect_intent_and_query()`。
- 多个测试在 Windows GBK 控制台打印 emoji，触发 `UnicodeEncodeError`。
- `UserRepository.batch_delete/batch_toggle` 现在返回元组，旧测试仍断言整数。
- 用户创建与 FTS5 用例存在隔离或数据清理问题。
- 当前依赖未声明 `pytest`，但大量测试采用 pytest 风格函数，`unittest discover` 不会完整发现它们。

### 修复建议

- 明确统一测试框架，将 `pytest` 加入开发依赖。
- 删除或重写旧意图识别测试，改测 MCP 语义路由。
- 测试输出使用 ASCII 或在测试入口固定 UTF-8。
- 每个数据库测试使用独立临时数据库，并重置 Repository/密钥全局状态。
- CI 中强制全量测试通过后才能合并。

---

## BUG-002：登录限速器存在并发竞态

**严重性：低（建议 P2）**  
**CWE：CWE-362 Concurrent Execution using Shared Resource with Improper Synchronization**

### 证据

`LoginRateLimiter` 的全局 `_failures` 字典在 `check()`、`record_failure()`、`clear()` 和清理流程中读写，但没有锁。Tornado 主线程通常串行执行 Handler，不过未来线程化、测试并发或其他调用路径会造成计数丢失或遍历期间修改。

### 修复建议

使用锁保护复合读写，或将限速状态迁移至带原子操作和 TTL 的共享存储；同时增加并发登录失败测试。多进程部署时内存限速本身也无法跨进程生效。

---

## 建议修复顺序

1. 立即修复 SEC-001、SEC-002、SEC-003，并补充越权/XSS/SSRF 集成测试。
2. 修复 SEC-004，确保禁用、删号和改密能撤销会话。
3. 修复 SEC-005 至 SEC-007，限制凭证与资源风险。
4. 修复 BUG-001，使测试基线恢复可信；随后处理并发限速。

## 审计边界

- 本次未进行互联网依赖漏洞库匹配、动态浏览器攻击验证、真实内网 SSRF 探测或生产配置检查。
- 未发现明显的直接 SQL 注入：检索到的动态 SQL主要用于由代码生成的固定条件片段，值参数使用 SQLite 占位符。
- XSRF 已全局启用，但它不能替代逐接口授权、输出净化和会话撤销。
