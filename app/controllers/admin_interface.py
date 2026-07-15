"""
admin_interface.py — 管理侧接口管理控制器

提供可复用 API 接口模板的 CRUD、启停和测试能力，并为 API 型数字员工
提供接口选择/自动填充的数据源。
"""
import asyncio
import atexit
import concurrent.futures
import json
import re
import logging
import time
import urllib.parse

import tornado.web

from app.controllers.admin_base import AdminBaseHandler
from app.models.api_interface import (
    API_METHODS,
    ApiInterfaceRepository,
    normalize_api_method,
    normalize_headers,
    redact_sensitive_headers,
    restore_redacted_headers,
    validate_api_url_template,
)
from app.utils.security import has_crlf, validate_url_safe, write_audit_log
from app.utils.safe_http import SafeHttpError, safe_http_request

logger = logging.getLogger(__name__)

_interface_test_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="api-iface-test")
atexit.register(_interface_test_executor.shutdown, wait=True)


class InterfaceListHandler(AdminBaseHandler):
    """接口模板列表页。"""

    @tornado.web.authenticated
    def get(self):
        try:
            page = max(1, int(self.get_query_argument("page", 1)))
        except (ValueError, TypeError):
            page = 1
        keyword = self.get_query_argument("keyword", "").strip()
        rows, total = ApiInterfaceRepository.get_all(
            page=page, page_size=20, keyword=keyword
        )
        total_pages = max(1, (total + 20 - 1) // 20)
        stats = ApiInterfaceRepository.get_stats()

        self.render(
            "admin/interface_list.html",
            title="接口管理 — 瞭望与问数系统",
            username=self.current_user,
            interfaces=rows,
            page=page,
            total=total,
            total_pages=total_pages,
            keyword=keyword,
            stats=stats,
            msg=self.get_query_argument("msg", ""),
            xsrf_token=self.xsrf_token.decode() if isinstance(self.xsrf_token, bytes) else self.xsrf_token,
        )


class InterfaceFormHandler(AdminBaseHandler):
    """接口模板新增/编辑表单。"""

    @tornado.web.authenticated
    def get(self):
        interface_id = self.get_query_argument("id", None)
        interface = None
        if interface_id:
            try:
                interface = ApiInterfaceRepository.get_by_id(int(interface_id))
            except (ValueError, TypeError):
                self.write('<script>alert("无效的接口ID");window.history.back();</script>')
                return
            if not interface:
                self.write('<script>alert("接口模板不存在");window.history.back();</script>')
                return
            # 编辑页不回显 Authorization / Cookie / X-API-Key 等敏感 Header；
            # 提交未改动的脱敏 payload 时在 POST 中恢复为原始值。
            interface = dict(interface)
            interface["api_headers"] = redact_sensitive_headers(interface.get("api_headers", "{}"))

        self.render(
            "admin/interface_form.html",
            title="编辑接口" if interface else "新增接口",
            username=self.current_user,
            interface=interface,
            api_methods=API_METHODS,
        )

    @tornado.web.authenticated
    def post(self):
        interface_id = self.get_body_argument("id", None)
        name = self.get_body_argument("name", "").strip()
        description = self.get_body_argument("description", "").strip()
        api_url = self.get_body_argument("api_url", "").strip()
        api_method = normalize_api_method(self.get_body_argument("api_method", "GET"))
        api_headers_raw = self.get_body_argument("api_headers", "{}").strip() or "{}"
        api_params_template = self.get_body_argument("api_params_template", "").strip()
        response_render_template = self.get_body_argument("response_render_template", "").strip()
        api_secret_raw = self.get_body_argument("api_secret", "").strip()
        clear_secret = self.get_body_argument("clear_secret", "0") == "1"
        try:
            sort_order = int(self.get_body_argument("sort_order", 0))
        except (ValueError, TypeError):
            self.write('<script>alert("排序号格式不正确");window.history.back();</script>')
            return

        if not name:
            self.write('<script>alert("接口名称不能为空");window.history.back();</script>')
            return
        valid_url, reason = validate_api_url_template(api_url)
        if not valid_url:
            self.write(f'<script>alert("{reason}");window.history.back();</script>')
            return
        api_headers = normalize_headers(api_headers_raw)
        if api_headers is None:
            self.write('<script>alert("请求头必须是 JSON 对象，且不能包含换行字符");window.history.back();</script>')
            return
        if api_secret_raw and has_crlf(api_secret_raw):
            self.write('<script>alert("接口密钥包含非法换行字符");window.history.back();</script>')
            return

        if interface_id:
            try:
                interface_id_int = int(interface_id)
            except (ValueError, TypeError):
                self.write('<script>alert("无效的接口ID");window.history.back();</script>')
                return
            existing = ApiInterfaceRepository.get_by_id(interface_id_int)
            if not existing:
                self.write('<script>alert("接口模板不存在");window.history.back();</script>')
                return
            restored_headers = restore_redacted_headers(api_headers_raw, existing.get("api_headers", "{}"))
            if restored_headers is None:
                self.write('<script>alert("请求头必须是 JSON 对象，且不能包含换行字符");window.history.back();</script>')
                return
            api_headers = restored_headers
            ok = ApiInterfaceRepository.update(
                interface_id_int, name, description, api_url, api_method,
                api_headers, api_params_template, response_render_template,
                api_secret_raw if api_secret_raw else None,
                sort_order, clear_secret,
            )
            msg = "更新成功" if ok else "更新失败"
            write_audit_log(
                action="API_INTERFACE_UPDATE",
                username=self.current_user,
                target=f"api_interface:{interface_id_int}",
                detail=f"name={name}, method={api_method}",
                client_ip=self.request.remote_ip or "",
            )
        else:
            new_id = ApiInterfaceRepository.create(
                name, description, api_url, api_method, api_headers,
                api_params_template, response_render_template,
                api_secret_raw, sort_order,
            )
            msg = "创建成功" if new_id > 0 else "创建失败"
            if new_id > 0:
                write_audit_log(
                    action="API_INTERFACE_CREATE",
                    username=self.current_user,
                    target=f"api_interface:{new_id}",
                    detail=f"name={name}, method={api_method}",
                    client_ip=self.request.remote_ip or "",
                )

        self.redirect(f"/admin/interface?msg={urllib.parse.quote(msg)}")


class InterfaceDeleteHandler(AdminBaseHandler):
    """删除接口模板。"""

    @tornado.web.authenticated
    def post(self):
        try:
            interface_id = int(self.get_body_argument("id", 0))
        except (ValueError, TypeError):
            self.write('<script>alert("无效的接口ID");window.history.back();</script>')
            return
        interface = ApiInterfaceRepository.get_by_id(interface_id)
        name = interface.get("name", "unknown") if interface else "unknown"
        ApiInterfaceRepository.delete(interface_id)
        write_audit_log(
            action="API_INTERFACE_DELETE",
            username=self.current_user,
            target=f"api_interface:{interface_id}",
            detail=f"name={name}",
            client_ip=self.request.remote_ip or "",
        )
        self.redirect("/admin/interface?msg=已删除")


class InterfaceToggleHandler(AdminBaseHandler):
    """启用/禁用接口模板。"""

    @tornado.web.authenticated
    def post(self):
        try:
            interface_id = int(self.get_body_argument("id", 0))
        except (ValueError, TypeError):
            self.write('<script>alert("无效的接口ID");window.history.back();</script>')
            return
        status = ApiInterfaceRepository.toggle_enabled(interface_id)
        if status == -1:
            self.write('<script>alert("接口模板不存在");window.history.back();</script>')
            return
        write_audit_log(
            action="API_INTERFACE_TOGGLE",
            username=self.current_user,
            target=f"api_interface:{interface_id}",
            detail=f"status={'enabled' if status == 1 else 'disabled'}",
            client_ip=self.request.remote_ip or "",
        )
        self.redirect(f"/admin/interface?msg={'已启用' if status == 1 else '已禁用'}")


class InterfaceTestHandler(AdminBaseHandler):
    """接口测试：根据模板和测试消息发起一次安全 HTTP 请求。"""

    @tornado.web.authenticated
    async def post(self):
        interface = self._build_interface_from_request()
        if not interface:
            return
        message = self.get_body_argument("message", "test").strip() or "test"
        if len(message) > 2000:
            self.write({"code": 1, "msg": "测试消息过长（最多2000字符）"})
            return

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            _interface_test_executor,
            lambda: _execute_interface_sync(interface, message),
        )

        write_audit_log(
            action="API_INTERFACE_TEST",
            username=self.current_user,
            target=f"api_interface:{interface.get('id', 'draft')}",
            detail=f"status={result.get('status', 0)}, code={result.get('code', 1)}",
            client_ip=self.request.remote_ip or "",
        )
        self.write(result)

    def _build_interface_from_request(self) -> dict | None:
        """支持按 id 测试已保存接口，也支持测试表单中的草稿配置。"""
        interface_id = self.get_body_argument("id", "").strip()
        if interface_id:
            try:
                interface = ApiInterfaceRepository.get_by_id(int(interface_id))
            except (ValueError, TypeError):
                self.write({"code": 1, "msg": "无效的接口ID"})
                return None
            if not interface:
                self.write({"code": 1, "msg": "接口模板不存在"})
                return None
            return interface

        api_headers_raw = self.get_body_argument("api_headers", "{}").strip() or "{}"
        draft_id = self.get_body_argument("draft_id", "").strip()
        draft_existing = None
        if draft_id:
            try:
                draft_existing = ApiInterfaceRepository.get_by_id(int(draft_id))
            except (ValueError, TypeError):
                draft_existing = None
        if draft_existing:
            api_headers = restore_redacted_headers(api_headers_raw, draft_existing.get("api_headers", "{}"))
        else:
            api_headers = normalize_headers(api_headers_raw)
        if api_headers is None:
            self.write({"code": 1, "msg": "请求头必须是 JSON 对象，且不能包含换行字符"})
            return None

        api_secret = self.get_body_argument("api_secret", "").strip()
        clear_secret = self.get_body_argument("clear_secret", "0") == "1"
        if draft_existing and not api_secret and not clear_secret:
            api_secret = draft_existing.get("api_secret", "")
        if api_secret and has_crlf(api_secret):
            self.write({"code": 1, "msg": "接口密钥包含非法换行字符"})
            return None

        interface = {
            "id": None,
            "name": self.get_body_argument("name", "未保存接口").strip() or "未保存接口",
            "api_url": self.get_body_argument("api_url", "").strip(),
            "api_method": normalize_api_method(self.get_body_argument("api_method", "GET")),
            "api_headers": api_headers,
            "api_params_template": self.get_body_argument("api_params_template", "").strip(),
            "response_render_template": self.get_body_argument("response_render_template", "").strip(),
            "api_secret": api_secret,
        }
        valid, reason = validate_api_url_template(interface["api_url"])
        if not valid:
            self.write({"code": 1, "msg": reason})
            return None
        return interface


class InterfaceApiListHandler(AdminBaseHandler):
    """API: 启用接口模板列表，供数字员工表单联动选择。"""

    @tornado.web.authenticated
    def get(self):
        rows = ApiInterfaceRepository.get_enabled()
        items = [ApiInterfaceRepository.to_employee_payload(r) for r in rows]
        self.write({"code": 0, "items": items})


def _render_url_template(template: str, message: str) -> str:
    encoded = urllib.parse.quote(message, safe="", encoding="utf-8")
    return (template or "").replace("{message}", encoded).replace("{message_raw}", encoded)


def _render_param_template(template: str, message: str) -> str:
    encoded = urllib.parse.quote(message, safe="", encoding="utf-8")
    return (template or "").replace("{message}", encoded).replace("{message_raw}", message)


def _execute_interface_sync(interface: dict, message: str) -> dict:
    """同步执行接口测试（在线程池中调用）。"""
    start = time.time()
    api_url = _render_url_template(interface.get("api_url", ""), message)
    api_method = normalize_api_method(interface.get("api_method", "GET"))
    api_params = _render_param_template(interface.get("api_params_template", ""), message)

    try:
        headers = json.loads(interface.get("api_headers", "{}") or "{}")
        if not isinstance(headers, dict):
            headers = {}
    except (json.JSONDecodeError, TypeError):
        headers = {}
    headers = {str(k): str(v) for k, v in headers.items()}
    api_secret = interface.get("api_secret", "")
    if api_secret and not any(str(k).lower() == "authorization" for k in headers):
        headers["Authorization"] = f"Bearer {api_secret}"

    request_url = api_url
    data = None
    if api_method == "GET" and api_params:
        request_url += ("&" if "?" in request_url else "?") + api_params
    elif api_params:
        data = api_params.encode("utf-8")

    # URL 编码非 ASCII 字符，保持查询分隔符等 URL 结构字符。
    request_url = urllib.parse.quote(
        request_url, safe=":/?#[]@!$&'()*+,;=%-", encoding="utf-8"
    )

    safe, reason, _ = validate_url_safe(request_url)
    if not safe:
        return {"code": 1, "msg": f"API URL 不安全: {reason}", "status": 0}

    try:
        resp = safe_http_request(
            request_url,
            method=api_method,
            headers=headers,
            body=data,
            timeout=30,
            max_bytes=256 * 1024,
        )
        body = resp.body.decode("utf-8", errors="replace")
        elapsed_ms = int((time.time() - start) * 1000)
        def redact(value):
            sensitive = ("authorization", "token", "api_key", "apikey", "secret", "password", "credential", "session")
            if isinstance(value, dict):
                return {k: ("[REDACTED]" if any(part in str(k).lower() for part in sensitive) else redact(v)) for k, v in value.items()}
            if isinstance(value, list):
                return [redact(item) for item in value[:100]]
            return value

        try:
            parsed_body = redact(json.loads(body))
            display_body = json.dumps(parsed_body, ensure_ascii=False)[:5000]
        except json.JSONDecodeError:
            parsed_body = None
            display_body = body[:1000]
            display_body = re.sub(
                r"(?i)(access_token|refresh_token|id_token|client_secret|api_key|password)=([^&\s]+)",
                r"\1=[REDACTED]",
                display_body,
            )
            display_body = re.sub(r"(?i)Bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", display_body)

        secret_headers = {"set-cookie", "www-authenticate", "authorization", "proxy-authenticate"}
        display_headers = {
            key: ("[REDACTED]" if str(key).lower() in secret_headers else value)
            for key, value in resp.headers.items()
        }
        result = {
            "code": 0 if resp.status < 400 else 1,
            "msg": "测试成功" if resp.status < 400 else f"HTTP {resp.status}: {resp.reason}",
            "status": resp.status,
            "elapsed_ms": elapsed_ms,
            "headers": display_headers,
            "raw": display_body,
            "truncated": len(body) > len(display_body),
        }
        result["data"] = parsed_body if parsed_body is not None else {"raw": display_body}
        return result
    except SafeHttpError as e:
        return {
            "code": 1,
            "msg": str(e),
            "status": 0,
            "elapsed_ms": int((time.time() - start) * 1000),
        }
    except Exception as e:
        logger.warning("接口测试失败: %s", e)
        return {
            "code": 1,
            "msg": f"接口调用失败: {e}",
            "status": 0,
            "elapsed_ms": int((time.time() - start) * 1000),
        }
