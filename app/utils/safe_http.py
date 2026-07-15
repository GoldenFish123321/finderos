"""
safe_http.py — 安全 HTTP 调用工具

用于接口管理测试与 API 型数字员工调用，统一处理：
- SSRF URL 校验
- DNS 解析结果固定（避免二次解析 / DNS Rebinding TOCTOU）
- 禁止自动重定向（避免 30x 跳转到内网）
- Header CRLF 校验
"""
from __future__ import annotations

import http.client
import re
import ssl
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse

from app.utils.security import has_crlf, validate_url_safe


class SafeHttpError(Exception):
    """安全 HTTP 调用失败。"""


@dataclass
class SafeHttpResponse:
    status: int
    reason: str
    headers: dict
    body: bytes
    resolved_ip: str


_HTTP_METHOD_RE = re.compile(r"^[A-Z][A-Z0-9!#$%&'*+.^_`|~-]*$")


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """连接到已校验 IP，但保留原 hostname 用于 SNI 与证书校验。"""

    def __init__(self, connect_host: str, server_hostname: str, *args, **kwargs):
        super().__init__(server_hostname, *args, **kwargs)
        self._connect_host = connect_host
        self._server_hostname = server_hostname

    def connect(self):
        self.sock = self._create_connection(
            (self._connect_host, self.port),
            self.timeout,
            self.source_address,
        )
        if self._tunnel_host:
            self._tunnel()
        self.sock = self._context.wrap_socket(
            self.sock,
            server_hostname=self._server_hostname,
        )


def _target_path(parsed) -> str:
    return urlunparse(("", "", parsed.path or "/", parsed.params, parsed.query, ""))


def _validate_headers(headers: dict | None) -> dict:
    clean = {}
    for key, value in (headers or {}).items():
        key_str = str(key)
        value_str = str(value)
        if has_crlf(key_str) or has_crlf(value_str):
            raise SafeHttpError("Header 包含非法字符（CR/LF）")
        clean[key_str] = value_str
    return clean


def safe_http_request(
    url: str,
    method: str = "GET",
    headers: dict | None = None,
    body: bytes | None = None,
    timeout: int = 30,
    max_bytes: int = 256 * 1024,
) -> SafeHttpResponse:
    """发起一次安全 HTTP 请求。

    注意：本函数不自动跟随重定向；调用方应将 3xx 当作普通响应处理，
    或对 Location 重新做安全校验后再显式请求。
    """
    safe, reason, resolved_ip = validate_url_safe(url)
    if not safe:
        raise SafeHttpError(f"API URL 不安全: {reason}")

    parsed = urlparse(url)
    if not parsed.hostname:
        raise SafeHttpError("URL 缺少主机名")

    method = (method or "GET").strip().upper()
    if not _HTTP_METHOD_RE.fullmatch(method):
        raise SafeHttpError("HTTP Method 包含非法字符")
    request_headers = _validate_headers(headers)
    default_port = 443 if parsed.scheme.lower() == "https" else 80
    port = parsed.port or default_port
    host_header = parsed.hostname
    if parsed.port and parsed.port != default_port:
        host_header = f"{parsed.hostname}:{parsed.port}"
    # Host 必须与已安全校验的 URL host 保持一致，避免自定义 Host 头造成
    # 虚拟主机/代理层面的安全边界绕过。HTTP Header 大小写不敏感，
    # 先移除用户传入的任意大小写 Host，再写入唯一 canonical Host。
    request_headers = {
        key: value for key, value in request_headers.items()
        if str(key).lower() != "host"
    }
    request_headers["Host"] = host_header

    if parsed.scheme.lower() == "https":
        conn = _PinnedHTTPSConnection(
            resolved_ip,
            parsed.hostname,
            port=port,
            timeout=timeout,
            context=ssl.create_default_context(),
        )
    else:
        conn = http.client.HTTPConnection(resolved_ip, port=port, timeout=timeout)

    try:
        conn.request(method, _target_path(parsed), body=body, headers=request_headers)
        resp = conn.getresponse()
        data = resp.read(max_bytes + 1)
        return SafeHttpResponse(
            status=resp.status,
            reason=resp.reason,
            headers=dict(resp.getheaders()),
            body=data[:max_bytes],
            resolved_ip=resolved_ip,
        )
    finally:
        conn.close()
