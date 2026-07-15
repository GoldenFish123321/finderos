"""
api_interface.py — 接口管理 Repository

管理可复用的 HTTP API 接口模板，供 API 型数字员工选择并自动填充
URL、Method、Headers、参数模板和响应渲染模板。
"""
import json
import sqlite3
from urllib.parse import urlparse

from app.models.db import get_db
from app.utils.security import decrypt_api_key, encrypt_api_key, has_crlf


API_METHODS = [
    {"value": "GET", "name": "GET"},
    {"value": "POST", "name": "POST"},
    {"value": "PUT", "name": "PUT"},
    {"value": "PATCH", "name": "PATCH"},
    {"value": "DELETE", "name": "DELETE"},
]

_METHOD_VALUES = {m["value"] for m in API_METHODS}
REDACTED_SECRET = "******"
SENSITIVE_HEADER_NAMES = {
    "authorization",
    "proxy-authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "api-key",
    "x-auth-token",
    "x-access-token",
}


def normalize_api_method(method: str) -> str:
    """规范化并校验 HTTP Method。"""
    method = (method or "GET").strip().upper()
    return method if method in _METHOD_VALUES else "GET"


def normalize_headers(headers_raw: str) -> str | None:
    """校验并规范化 Headers JSON；非法时返回 None。"""
    headers_raw = (headers_raw or "{}").strip() or "{}"
    try:
        parsed = json.loads(headers_raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(parsed, dict):
        return None
    # Header key/value 不允许换行，避免 CRLF 注入。
    for key, value in parsed.items():
        if has_crlf(str(key)) or has_crlf(str(value)):
            return None
    return json.dumps(parsed, ensure_ascii=False)


def redact_sensitive_headers(headers_raw: str) -> str:
    """对敏感 Header 值脱敏后返回 JSON 字符串。"""
    normalized = normalize_headers(headers_raw)
    if normalized is None:
        return "{}"
    parsed = json.loads(normalized)
    for key in list(parsed.keys()):
        if str(key).lower() in SENSITIVE_HEADER_NAMES:
            parsed[key] = REDACTED_SECRET
    return json.dumps(parsed, ensure_ascii=False)


def is_redacted_header_payload(headers_raw: str, original_headers_raw: str) -> bool:
    """判断提交的 headers 是否等于原始 headers 的脱敏形式。"""
    submitted = normalize_headers(headers_raw)
    redacted = normalize_headers(redact_sensitive_headers(original_headers_raw))
    return submitted is not None and redacted is not None and submitted == redacted


def restore_redacted_headers(headers_raw: str, original_headers_raw: str) -> str | None:
    """恢复提交 payload 中未修改的敏感 Header。

    编辑表单/联动 API 会把 Authorization、Cookie、X-API-Key 等敏感 Header
    展示为 ``******``。用户可能只调整非敏感 Header 或重新格式化 JSON，
    此时不能把真实敏感值静默覆盖为字面量 ``******``。

    返回规范化后的 JSON 字符串；如果提交值不是合法 Header JSON，则返回 None。
    """
    submitted = normalize_headers(headers_raw)
    if submitted is None:
        return None
    submitted_obj = json.loads(submitted)

    original = normalize_headers(original_headers_raw)
    original_obj = json.loads(original) if original is not None else {}
    original_by_lower = {str(k).lower(): v for k, v in original_obj.items()}

    for key, value in list(submitted_obj.items()):
        key_lower = str(key).lower()
        if (
            key_lower in SENSITIVE_HEADER_NAMES
            and str(value) == REDACTED_SECRET
            and key_lower in original_by_lower
        ):
            submitted_obj[key] = original_by_lower[key_lower]

    return json.dumps(submitted_obj, ensure_ascii=False)


def validate_api_url_template(url: str) -> tuple[bool, str]:
    """轻量校验接口模板 URL，允许包含 {message} 等占位符。"""
    url = (url or "").strip()
    if not url:
        return False, "接口 URL 不能为空"
    if has_crlf(url):
        return False, "接口 URL 包含非法换行字符"
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "接口 URL 解析失败"
    if parsed.scheme.lower() not in ("http", "https"):
        return False, "接口 URL 仅支持 http/https"
    if not parsed.hostname:
        return False, "接口 URL 缺少主机名"
    return True, ""


def _decrypt_interface_secrets(row_dict: dict) -> dict:
    """解密接口模板中的敏感字段。"""
    if row_dict.get("api_secret"):
        row_dict["api_secret"] = decrypt_api_key(row_dict["api_secret"])
    return row_dict


class ApiInterfaceRepository:
    """接口模板数据访问类。"""

    @staticmethod
    def get_all(page: int = 1, page_size: int = 20, keyword: str = "",
                enabled_only: bool = False) -> tuple[list[dict], int]:
        """分页查询接口模板。返回 (rows, total)。"""
        with get_db() as conn:
            conditions = []
            params = []
            if keyword:
                conditions.append("(name LIKE ? OR description LIKE ? OR api_url LIKE ?)")
                like = f"%{keyword}%"
                params.extend([like, like, like])
            if enabled_only:
                conditions.append("is_enabled = 1")
            where = "WHERE " + " AND ".join(conditions) if conditions else ""
            total = conn.execute(
                f"SELECT COUNT(*) as cnt FROM api_interfaces {where}", params
            ).fetchone()["cnt"]
            rows = conn.execute(
                f"SELECT * FROM api_interfaces {where} "
                f"ORDER BY sort_order ASC, id ASC LIMIT ? OFFSET ?",
                (*params, page_size, (page - 1) * page_size),
            ).fetchall()
        return [_decrypt_interface_secrets(dict(r)) for r in rows], total

    @staticmethod
    def get_enabled() -> list[dict]:
        """获取所有启用接口模板。"""
        rows, _ = ApiInterfaceRepository.get_all(page=1, page_size=1000, enabled_only=True)
        return rows

    @staticmethod
    def get_for_employee_form(current_interface_id: int | None = None) -> list[dict]:
        """获取员工表单可选接口；当前绑定接口即使禁用也保留显示。"""
        enabled = ApiInterfaceRepository.get_enabled()
        seen = {r["id"] for r in enabled}
        if current_interface_id and current_interface_id not in seen:
            current = ApiInterfaceRepository.get_by_id(current_interface_id)
            if current:
                enabled.append(current)
        return [ApiInterfaceRepository.to_employee_payload(r) for r in enabled]

    @staticmethod
    def get_by_id(interface_id: int) -> dict | None:
        """按 ID 获取接口模板。"""
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM api_interfaces WHERE id = ?", (interface_id,)
            ).fetchone()
        if not row:
            return None
        return _decrypt_interface_secrets(dict(row))

    @staticmethod
    def create(name: str, description: str = "", api_url: str = "",
               api_method: str = "GET", api_headers: str = "{}",
               api_params_template: str = "", response_render_template: str = "",
               api_secret: str = "", sort_order: int = 0) -> int:
        """创建接口模板。返回新 ID，失败返回 -1。"""
        name = (name or "").strip()
        api_url = (api_url or "").strip()
        api_method = normalize_api_method(api_method)
        api_headers = normalize_headers(api_headers)
        valid_url, _ = validate_api_url_template(api_url)
        if not name or not valid_url or api_headers is None or (api_secret and has_crlf(api_secret)):
            return -1
        try:
            encrypted_secret = encrypt_api_key(api_secret.strip()) if api_secret else ""
            with get_db() as conn:
                cur = conn.execute(
                    "INSERT INTO api_interfaces (name, description, api_url, api_method, "
                    "api_headers, api_params_template, response_render_template, "
                    "api_secret, sort_order) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        name, (description or "").strip(), api_url, api_method,
                        api_headers, api_params_template or "",
                        response_render_template or "", encrypted_secret, sort_order,
                    ),
                )
                conn.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return -1

    @staticmethod
    def update(interface_id: int, name: str, description: str = "",
               api_url: str = "", api_method: str = "GET",
               api_headers: str = "{}", api_params_template: str = "",
               response_render_template: str = "", api_secret: str | None = None,
               sort_order: int = 0, clear_secret: bool = False) -> bool:
        """更新接口模板。api_secret 为 None 时保留旧密钥。"""
        name = (name or "").strip()
        api_url = (api_url or "").strip()
        api_method = normalize_api_method(api_method)
        api_headers = normalize_headers(api_headers)
        valid_url, _ = validate_api_url_template(api_url)
        if not name or not valid_url or api_headers is None or (api_secret and has_crlf(api_secret)):
            return False
        try:
            if clear_secret:
                encrypted_secret = ""
            elif api_secret is None:
                existing = ApiInterfaceRepository.get_by_id(interface_id)
                encrypted_secret = encrypt_api_key(existing.get("api_secret", "")) if existing and existing.get("api_secret") else ""
            else:
                encrypted_secret = encrypt_api_key(api_secret.strip()) if api_secret else ""
            with get_db() as conn:
                cursor = conn.execute(
                    "UPDATE api_interfaces SET name=?, description=?, api_url=?, api_method=?, "
                    "api_headers=?, api_params_template=?, response_render_template=?, "
                    "api_secret=?, sort_order=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (
                        name, (description or "").strip(), api_url, api_method,
                        api_headers, api_params_template or "",
                        response_render_template or "", encrypted_secret,
                        sort_order, interface_id,
                    ),
                )
                conn.commit()
            return cursor.rowcount > 0
        except sqlite3.IntegrityError:
            return False

    @staticmethod
    def delete(interface_id: int) -> bool:
        """删除接口模板。"""
        with get_db() as conn:
            conn.execute(
                "UPDATE digital_employees SET api_interface_id = NULL WHERE api_interface_id = ?",
                (interface_id,),
            )
            cursor = conn.execute("DELETE FROM api_interfaces WHERE id = ?", (interface_id,))
            conn.commit()
            return cursor.rowcount > 0

    @staticmethod
    def toggle_enabled(interface_id: int) -> int:
        """切换启用/禁用状态。返回新状态 (0/1) 或 -1。"""
        with get_db() as conn:
            row = conn.execute(
                "SELECT is_enabled FROM api_interfaces WHERE id = ?", (interface_id,)
            ).fetchone()
            if not row:
                return -1
            new_status = 0 if row["is_enabled"] == 1 else 1
            conn.execute(
                "UPDATE api_interfaces SET is_enabled=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (new_status, interface_id),
            )
            conn.commit()
            return new_status

    @staticmethod
    def get_stats() -> dict:
        """获取接口模板统计信息。"""
        with get_db() as conn:
            total = conn.execute("SELECT COUNT(*) as cnt FROM api_interfaces").fetchone()["cnt"]
            enabled = conn.execute(
                "SELECT COUNT(*) as cnt FROM api_interfaces WHERE is_enabled = 1"
            ).fetchone()["cnt"]
            return {"total": total, "enabled": enabled}

    @staticmethod
    def get_count() -> int:
        """获取接口模板总数。"""
        with get_db() as conn:
            return conn.execute("SELECT COUNT(*) as cnt FROM api_interfaces").fetchone()["cnt"]

    @staticmethod
    def to_employee_payload(interface: dict) -> dict:
        """将接口模板转成数字员工表单/接口返回可用的字段。"""
        return {
            "id": interface.get("id"),
            "name": interface.get("name", ""),
            "description": interface.get("description", ""),
            "api_url": interface.get("api_url", ""),
            "api_method": interface.get("api_method", "GET"),
            "api_headers": redact_sensitive_headers(interface.get("api_headers", "{}")),
            "api_params_template": interface.get("api_params_template", ""),
            "response_render_template": interface.get("response_render_template", ""),
            "has_secret": bool(interface.get("api_secret")),
            "is_enabled": interface.get("is_enabled", 0),
        }
