"""
security.py — 安全工具模块

提供 SSRF 防护 URL 校验 + API Key 加密存储 + 审计日志写入。
参考 OWASP Top 10 (2021): A10: Server-Side Request Forgery (SSRF)
"""

import base64
import hashlib
import ipaddress
import logging
import os
import re
import secrets
import socket
import stat
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

from cryptography.fernet import Fernet

from app.config.settings import settings
from app.models.db import get_db

logger = logging.getLogger(__name__)

# ── .secret_key 文件路径（与 main.py 中的定义保持一致）──
_SECRET_KEY_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    ".secret_key"
)

# ── CRLF 注入检测 ──────────────────────────────────────────────
_CRLF_PATTERN = re.compile(r"[\r\n]")


def has_crlf(value: str) -> bool:
    """检测字符串是否包含 CR/LF（防止 HTTP Header 注入）。"""
    return bool(_CRLF_PATTERN.search(value))


def sanitize_log_value(value: str) -> str:
    """移除字符串中的 CR/LF 字符，防止日志注入攻击。

    日志注入（Log Injection / CRLF Injection）攻击者可在用户输入中
    嵌入换行符来伪造日志条目，破坏审计日志的完整性。

    参考：OWASP A09:2021 Security Logging and Monitoring Failures
    CWE-117: Improper Output Neutralization for Logs
    """
    if not value:
        return value
    return _CRLF_PATTERN.sub("", value)


# ── Prompt Injection 检测 ─────────────────────────────────────

# 危险指令模式（匹配已知的 Prompt Injection / Jailbreak 攻击模式）
_PROMPT_INJECTION_PATTERNS = [
    re.compile(r"(?i)(ignore|forget|disregard)\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions?|prompts?|rules?|constraints?)"),
    re.compile(r"(?i)you\s+are\s+now\s+(DAN|STAN|jailbroken|unchained|unleashed)"),
    re.compile(r"(?i)pretend\s+(you\s+are|to\s+be)\s+(a\s+)?(different|another|new)"),
    re.compile(r"(?i)system\s*(prompt|message|instruction)\s*(is|:|=)"),
    re.compile(r"(?i)(DROP|DELETE|ALTER|TRUNCATE)\s+(TABLE|DATABASE|INDEX)"),
    re.compile(r"(?i)SELECT\s+.*\s+FROM\s+.*\s+WHERE.*(--|;)"),
    re.compile(r"(?i)<script[^>]*>|javascript\s*:|onerror\s*=|onload\s*="),
    re.compile(r"(?i)(output|show|reveal|display|print|disclose)\s+(your|the)\s+(system\s+)?(prompt|instructions?|rules?)"),
    re.compile(r"(?i)(为你|假装|忽略|忘记|跳过)\s*(之前的|所有的|前面的)?\s*(指令|提示|规则|约束|限制)"),
]


def detect_prompt_injection(user_input: str) -> tuple[bool, str]:
    """检测用户输入中是否包含 Prompt Injection / SQL 注入 / XSS 攻击模式。

    Returns:
        (is_attack, matched_pattern_description)
    """
    if not user_input:
        return False, ""

    for pattern in _PROMPT_INJECTION_PATTERNS:
        match = pattern.search(user_input)
        if match:
            return True, f"检测到潜在安全风险: {match.group(0)[:50]}"

    # 检测过长的重复模式（DoS）
    if len(user_input) > 5000:
        # 检查重复字符比例
        unique_ratio = len(set(user_input)) / len(user_input)
        if unique_ratio < 0.05:
            return True, "检测到异常重复输入模式"

    return False, ""


def sanitize_user_input(user_input: str) -> str:
    """清洗用户输入：移除明显的危险字符序列，保留正常内容。

    注意：此处采用"轻量过滤"策略，不彻底修改原文，
    仅在明显攻击模式时做替换。主要的防护依赖 Prompt 层的指令隔离。
    """
    if not user_input:
        return ""

    cleaned = user_input
    # 移除 SQL 关键字注入尝试
    for keyword in ["DROP TABLE", "DROP DATABASE", "ALTER TABLE", "TRUNCATE TABLE",
                     "DELETE FROM", "INSERT INTO", "UPDATE SET"]:
        cleaned = re.sub(rf"(?i){keyword}", "[BLOCKED]", cleaned)

    return cleaned


# ── XSS 防护：HTML 清洗与 JSON 安全序列化 ─────────────────────


def sanitize_html(value: str) -> str:
    """对字符串进行 HTML 实体转义，防止 XSS 攻击。

    将 < > & " ' 转义为对应的 HTML 实体。
    用于清洗从数据库读取的用户输入数据，确保在模板中安全渲染。

    参考: OWASP XSS Prevention Cheat Sheet, Rule #1
    """
    if not value:
        return value
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


def sanitize_json_data(data):
    """递归清洗数据结构中的所有字符串值，防止 XSS。

    对 dict/list 中的每个字符串值调用 sanitize_html()，
    确保通过 {% raw json_encode(...) %} 嵌入模板的数据是安全的。

    注意：此函数不会修改 HTML 中已包含的安全标签（如 <i>），
    它只清洗来自用户/数据库的纯文本字段。
    如果某个字段包含合法的 HTML 片段，调用方应在构建数据
    结构前先对用户输入部分做清洗，而非对整个字段调用此函数。

    Args:
        data: 待清洗的数据结构（dict / list / str / 其他基本类型）

    Returns:
        清洗后的数据结构（保持原类型）
    """
    if isinstance(data, dict):
        return {k: sanitize_json_data(v) for k, v in data.items()}
    if isinstance(data, list):
        return [sanitize_json_data(item) for item in data]
    if isinstance(data, str):
        return sanitize_html(data)
    return data


def sanitize_untrusted_llm_context(value, max_length: int = 12000) -> str:
    """Serialize tool/web data as bounded, explicitly untrusted LLM context."""
    import json
    text = value if isinstance(value, str) else json.dumps(
        value, ensure_ascii=False, default=str
    )
    text = text.replace("\x00", "").replace("```", "''' ")
    replacements = {
        "[SYSTEM]": "[DATA-SYSTEM]",
        "[ASSISTANT]": "[DATA-ASSISTANT]",
        "<system>": "[system]",
        "</system>": "[/system]",
        "<assistant>": "[assistant]",
        "</assistant>": "[/assistant]",
    }
    for token, replacement in replacements.items():
        text = text.replace(token, replacement)
    return text[:max_length]


# ── SSRF 防护 ──────────────────────────────────────────────────


def _is_ip_in_ranges(ip_str: str, cidr_list: list[str]) -> bool:
    """检查 IP 是否在给定的 CIDR 网段列表中。"""
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    for cidr in cidr_list:
        try:
            if "/" in cidr:
                if addr in ipaddress.ip_network(cidr, strict=False):
                    return True
            else:
                if addr == ipaddress.ip_address(cidr):
                    return True
        except ValueError:
            continue
    return False


def validate_url_safe(url: str) -> tuple[bool, str, str]:
    """
    SSRF 防护校验：检查 URL 是否安全可用。

    返回 (is_safe, reason, resolved_ip)。
    拦截条件：
    1. 仅允许 http/https 协议
    2. 不允许包含 CR/LF（防 Header 注入）
    3. 不允许指向内网/回环地址
    4. 不允许空 hostname

    同时返回已解析的 IP 地址（防 DNS 重绑定 TOCTOU 攻击）：
    调用方应使用 resolved_ip 直接发起请求，避免二次 DNS 解析。
    详见 GitHub Issue #11。
    """
    if not url:
        return False, "URL 为空", ""

    # CRLF 检测
    if has_crlf(url):
        return False, "URL 包含非法字符（CR/LF）", ""

    try:
        parsed = urlparse(url)
    except Exception:
        return False, "URL 解析失败", ""

    # 协议白名单
    if parsed.scheme.lower() not in settings.SSRF_ALLOWED_SCHEMES:
        return False, f"不支持的协议: {parsed.scheme}", ""

    # 必须有 hostname
    hostname = parsed.hostname
    if not hostname:
        return False, "URL 缺少主机名", ""

    # Resolve every A/AAAA result. A hostname is unsafe if any answer is private;
    # checking a single answer permits round-robin and dual-stack bypasses.
    try:
        addr_infos = socket.getaddrinfo(hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return False, f"无法解析主机名: {hostname}", ""
    ips = list(dict.fromkeys(info[4][0] for info in addr_infos))
    if not ips:
        return False, f"无法解析主机名: {hostname}", ""
    for ip in ips:
        try:
            address = ipaddress.ip_address(ip)
        except ValueError:
            return False, f"主机名解析结果无效: {hostname}", ""
        if not address.is_global or _is_ip_in_ranges(ip, settings.SSRF_BLOCKED_HOSTS):
            return False, f"禁止访问非公网地址: {hostname} ({ip})", ""

    return True, "", ips[0]


def pin_url_to_ip(url: str, resolved_ip: str) -> tuple[str, dict]:
    """
    将 URL 中的 hostname 替换为已解析的 IP，并返回需要设置的 Host 头。

    防止 DNS 重绑定 TOCTOU 攻击：调用方应在 DNS 解析后
    使用本函数构造 IP 固定的请求 URL 和 Host 头，
    避免 urllib 在发起请求时进行二次 DNS 解析。

    Args:
        url: 原始 URL
        resolved_ip: 已验证的 IP 地址（来自 validate_url_safe）

    Returns:
        (pinned_url, extra_headers): pinned_url 为 IP 替换后的 URL，
        extra_headers 为需要合并到请求头的 {"Host": "..."} 字典。
    """
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL 缺少 hostname")

    # 构造新的 netloc（使用 IP 替换 hostname）
    default_port = 443 if parsed.scheme == "https" else 80
    if parsed.port and parsed.port != default_port:
        netloc = f"{resolved_ip}:{parsed.port}"
        host_header = f"{hostname}:{parsed.port}"
    else:
        netloc = resolved_ip
        host_header = hostname

    pinned_url = parsed._replace(netloc=netloc).geturl()
    extra_headers = {"Host": host_header}

    return pinned_url, extra_headers


# ── API Key 加密存储 ──────────────────────────────────────────

# Fernet 实例缓存（延迟初始化，避免循环导入）
_fernet_instance: Fernet | None = None


def _ensure_secret_key() -> str:
    """确保 COOKIE_SECRET 已初始化，按优先级从多处来源加载。

    优先级：
    1. settings.COOKIE_SECRET（环境变量或 main.py 已注入）
    2. .secret_key 文件（持久化密钥，跨重启保持一致）
    3. 自动生成新密钥并保存到 .secret_key 文件

    这确保 API Key 加密模块在任何入口点（main.py、make_admin.py、
    migrate_db.py、测试脚本等）都能获得一致的加密密钥。
    """
    secret = settings.COOKIE_SECRET
    if secret:
        return secret

    # 尝试从 .secret_key 文件加载
    try:
        if os.path.exists(_SECRET_KEY_FILE):
            with open(_SECRET_KEY_FILE, "r") as f:
                saved = f.read().strip()
                if saved:
                    logger.info("已从 .secret_key 文件加载密钥用于 API Key 加密")
                    # 同步回 settings，避免后续重复读取文件
                    settings.COOKIE_SECRET = saved
                    return saved
    except OSError as e:
        logger.warning(f"读取 .secret_key 文件失败: {e}")

    # 生成新密钥并持久化
    new_secret = secrets.token_hex(32)
    try:
        with open(_SECRET_KEY_FILE, "w") as f:
            f.write(new_secret)
        # 设置安全权限：仅所有者可读写 (600)，防止其他用户读取密钥
        os.chmod(_SECRET_KEY_FILE, stat.S_IRUSR | stat.S_IWUSR)
        logger.info("已生成新的密钥并保存到 .secret_key 文件（用于 API Key 加密）")
    except OSError as e:
        logger.warning(f"无法保存 .secret_key 文件: {e}，密钥仅存在于本次会话")

    # 同步回 settings
    settings.COOKIE_SECRET = new_secret
    return new_secret


def _get_fernet() -> Fernet:
    """获取或创建 Fernet 加密实例（从应用 secret 派生密钥）。

    密钥来源优先级：
    1. 环境变量 COOKIE_SECRET
    2. .secret_key 持久化文件
    3. 自动生成（保存到 .secret_key）

    绝不允许使用硬编码回退密钥，那会使加密形同虚设。
    """
    global _fernet_instance
    if _fernet_instance is not None:
        return _fernet_instance
    secret = _ensure_secret_key()
    if not secret:
        raise RuntimeError(
            "无法初始化 API Key 加密模块：未能获取有效的加密密钥。"
            "请设置 COOKIE_SECRET 环境变量或确保 .secret_key 文件可读写。"
        )
    derived = hashlib.sha256(secret.encode()).digest()
    fernet_key = base64.urlsafe_b64encode(derived)
    _fernet_instance = Fernet(fernet_key)
    return _fernet_instance


def encrypt_api_key(plaintext: str) -> str:
    """
    加密 API Key。

    空字符串不加密，直接返回空字符串。
    加密失败时抛出异常（fail-secure：绝不允许明文静默落库）。
    """
    if not plaintext:
        return ""
    f = _get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt_api_key(ciphertext: str) -> str:
    """
    解密 API Key。

    空字符串直接返回。
    如果解密失败（如密钥轮换导致无法解密），记录错误日志并返回原始值。
    注意：返回原始密文意味着 API 调用将使用无效密钥而失败，
    这比静默回退更安全（fail-secure 原则）。
    """
    if not ciphertext:
        return ""
    try:
        f = _get_fernet()
        return f.decrypt(ciphertext.encode()).decode()
    except Exception as e:
        # 解密失败：密钥可能已轮换或数据损坏
        logger.error(
            f"API Key 解密失败，密钥可能已轮换或数据损坏。"
            f"请检查 COOKIE_SECRET 是否与加密时一致。错误: {e}"
        )
        # 如果是明显的 Fernet 密文（以 gAAAAAB 开头），说明密钥不匹配
        # 返回空字符串触发 API Key 缺失提示，而非使用乱码作为密钥
        if ciphertext.startswith("gAAAAAB"):
            logger.critical(
                "检测到 Fernet 密文但解密失败 — COOKIE_SECRET 已更改！"
                "所有已加密的 API Key 将不可用。请恢复原始 COOKIE_SECRET。"
            )
            return ""
        # 可能是旧明文数据，直接返回原值（向后兼容）
        return ciphertext


# ── 密码强度校验 ──────────────────────────────────────────────


def validate_password_strength(password: str) -> tuple[bool, str]:
    """验证密码强度。

    要求：
    - 最少 8 个字符
    - 至少包含 2 类字符（大写字母、小写字母、数字、特殊字符）

    Returns:
        (is_valid, error_message)
    """
    if not password:
        return False, "密码不能为空"

    if len(password) < 8:
        return False, "密码长度至少需要8个字符"

    categories = 0
    if re.search(r"[A-Z]", password):
        categories += 1
    if re.search(r"[a-z]", password):
        categories += 1
    if re.search(r"[0-9]", password):
        categories += 1
    if re.search(r"[^A-Za-z0-9]", password):
        categories += 1

    if categories < 2:
        return False, "密码必须包含至少两种字符类型（大写字母、小写字母、数字、特殊字符）"

    return True, ""


# ── 审计日志 ───────────────────────────────────────────────────


def write_audit_log(
    action: str,
    username: str = "",
    target: str = "",
    detail: str = "",
    client_ip: str = "",
):
    """
    写入操作审计日志。

    所有字符串参数均经过 sanitize_log_value() 处理，移除 CR/LF
    字符以防御日志注入攻击（CWE-117 / OWASP A09:2021）。

    Args:
        action: 操作类型 (LOGIN / LOGOUT / CREATE / UPDATE / DELETE / COLLECT / CHAT 等)
        username: 操作人
        target: 操作对象（如表名或资源ID）
        detail: 操作详情
        client_ip: 客户端 IP
    """
    if not settings.AUDIT_ENABLED:
        return

    # 防御日志注入：移除所有 CR/LF 字符
    action = sanitize_log_value(action)
    username = sanitize_log_value(username)
    target = sanitize_log_value(target)
    detail = sanitize_log_value(detail)
    client_ip = sanitize_log_value(client_ip)

    try:
        with get_db() as conn:
            conn.execute(
                """INSERT INTO audit_logs (action, username, target, detail, client_ip)
                   VALUES (?, ?, ?, ?, ?)""",
                (action, username, target, detail[:1000] if detail else "", client_ip),
            )
    except Exception as e:
        logger.warning(f"审计日志写入失败: {e}")
