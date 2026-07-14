"""
security.py — 安全工具模块

提供 SSRF 防护 URL 校验 + API Key 加密存储 + 审计日志写入。
参考 OWASP Top 10 (2021): A10: Server-Side Request Forgery (SSRF)
"""

import base64
import hashlib
import ipaddress
import logging
import re
import socket
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

from cryptography.fernet import Fernet

from app.config.settings import settings
from app.models.db import get_db

logger = logging.getLogger(__name__)

# ── CRLF 注入检测 ──────────────────────────────────────────────
_CRLF_PATTERN = re.compile(r"[\r\n]")


def has_crlf(value: str) -> bool:
    """检测字符串是否包含 CR/LF（防止 HTTP Header 注入）。"""
    return bool(_CRLF_PATTERN.search(value))


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


def validate_url_safe(url: str) -> tuple[bool, str]:
    """
    SSRF 防护校验：检查 URL 是否安全可用。

    返回 (is_safe, reason)。
    拦截条件：
    1. 仅允许 http/https 协议
    2. 不允许包含 CR/LF（防 Header 注入）
    3. 不允许指向内网/回环地址
    4. 不允许空 hostname

    注意: 存在 DNS 重绑定攻击窗口（TOCTOU），
    DNS 解析验证与实际 HTTP 请求之间 DNS 可能变化。
    如需更强的防护，建议在网络层（防火墙）限制出站流量。
    """
    if not url:
        return False, "URL 为空"

    # CRLF 检测
    if has_crlf(url):
        return False, "URL 包含非法字符（CR/LF）"

    try:
        parsed = urlparse(url)
    except Exception:
        return False, "URL 解析失败"

    # 协议白名单
    if parsed.scheme.lower() not in settings.SSRF_ALLOWED_SCHEMES:
        return False, f"不支持的协议: {parsed.scheme}"

    # 必须有 hostname
    hostname = parsed.hostname
    if not hostname:
        return False, "URL 缺少主机名"

    # DNS 解析 hostname → IP
    try:
        ip = socket.gethostbyname(hostname)
    except socket.gaierror:
        return False, f"无法解析主机名: {hostname}"

    # 检查是否命中内网/回环地址
    if _is_ip_in_ranges(ip, settings.SSRF_BLOCKED_HOSTS):
        return False, f"禁止访问内网地址: {hostname} ({ip})"

    return True, ""


# ── API Key 加密存储 ──────────────────────────────────────────

# Fernet 实例缓存（延迟初始化，避免循环导入）
_fernet_instance: Fernet | None = None


def _get_fernet() -> Fernet:
    """获取或创建 Fernet 加密实例（从应用 secret 派生密钥）。

    如果 COOKIE_SECRET 未设置，抛出 RuntimeError 拒绝启动——
    不允许使用硬编码回退密钥，那会使加密形同虚设。
    """
    global _fernet_instance
    if _fernet_instance is not None:
        return _fernet_instance
    secret = settings.COOKIE_SECRET
    if not secret:
        raise RuntimeError(
            "COOKIE_SECRET 环境变量未设置，无法初始化 API Key 加密模块。"
            "请设置 COOKIE_SECRET 环境变量后重启应用。"
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

    Args:
        action: 操作类型 (LOGIN / LOGOUT / CREATE / UPDATE / DELETE / COLLECT / CHAT 等)
        username: 操作人
        target: 操作对象（如表名或资源ID）
        detail: 操作详情
        client_ip: 客户端 IP
    """
    if not settings.AUDIT_ENABLED:
        return

    try:
        with get_db() as conn:
            conn.execute(
                """INSERT INTO audit_logs (action, username, target, detail, client_ip)
                   VALUES (?, ?, ?, ?, ?)""",
                (action, username, target, detail[:1000] if detail else "", client_ip),
            )
    except Exception as e:
        logger.warning(f"审计日志写入失败: {e}")
