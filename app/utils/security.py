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
    如果解密失败（如旧数据为明文、密钥轮换等），返回原始值作为回退。
    这确保了从明文到密文的平滑迁移。
    """
    if not ciphertext:
        return ""
    try:
        f = _get_fernet()
        return f.decrypt(ciphertext.encode()).decode()
    except Exception:
        # 解密失败：可能是旧明文数据，直接返回原值
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
