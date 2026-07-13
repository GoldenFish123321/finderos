"""
security.py — 安全工具模块

提供 SSRF 防护 URL 校验 + 审计日志写入。
参考 OWASP Top 10 (2021): A10: Server-Side Request Forgery (SSRF)
"""

import ipaddress
import logging
import re
import socket
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

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
            conn.commit()
    except Exception as e:
        logger.warning(f"审计日志写入失败: {e}")
