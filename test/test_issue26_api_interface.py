"""
Issue #26: 管理侧接口管理模块 — 修复/功能验证

覆盖：
- api_interfaces 表与 Repository CRUD
- Header/URL 安全校验
- 接口模板向 API 型数字员工联动字段转换，不泄露密钥
- API 型数字员工可保存 api_interface_id 关联
- 安全 HTTP 调用拒绝内网地址
"""
import os
import sys
import pytest
import asyncio
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.controllers import admin_employee, user_chat
from app.utils import safe_http as safe_http_module
from app.models.api_interface import (
    ApiInterfaceRepository,
    is_redacted_header_payload,
    normalize_headers,
    redact_sensitive_headers,
    restore_redacted_headers,
    validate_api_url_template,
)
from app.models.db import get_db, init_db
from app.models.digital_employee import DigitalEmployeeRepository
from app.utils.safe_http import SafeHttpError, SafeHttpResponse, safe_http_request


def setup_module():
    init_db()
    cleanup()


def teardown_module():
    cleanup()


def cleanup():
    with get_db() as conn:
        conn.execute("DELETE FROM digital_employees WHERE name LIKE ?", ("_issue26_%",))
        conn.execute("DELETE FROM api_interfaces WHERE name LIKE ?", ("_issue26_%",))
        conn.commit()


def test_api_interface_crud_and_employee_payload():
    """接口模板应能创建/查询，并转换成数字员工联动配置且不泄露密钥。"""
    interface_id = ApiInterfaceRepository.create(
        name="_issue26_weather_",
        description="Issue26测试接口",
        api_url="https://example.com/weather?q={message}",
        api_method="GET",
        api_headers='{"Accept":"application/json"}',
        api_params_template="lang=zh&raw={message_raw}",
        response_render_template='{"type":"weather_card"}',
        api_secret="issue26-secret",
        sort_order=99,
    )
    assert interface_id > 0

    iface = ApiInterfaceRepository.get_by_id(interface_id)
    assert iface["name"] == "_issue26_weather_"
    assert iface["api_method"] == "GET"
    assert iface["api_secret"] == "issue26-secret"

    payload = ApiInterfaceRepository.to_employee_payload(iface)
    assert payload["api_url"] == "https://example.com/weather?q={message}"
    assert payload["api_headers"] == '{"Accept": "application/json"}' or payload["api_headers"] == '{"Accept":"application/json"}'
    assert payload["has_secret"] is True
    assert "api_secret" not in payload

    rows, total = ApiInterfaceRepository.get_all(keyword="weather")
    assert total >= 1
    assert any(r["id"] == interface_id for r in rows)


def test_sensitive_headers_are_redacted_in_employee_payload():
    """接口列表/员工联动 payload 不应泄漏 Authorization 等敏感 Header。"""
    interface_id = ApiInterfaceRepository.create(
        name="_issue26_secret_header_",
        description="敏感 Header 脱敏测试",
        api_url="https://example.com/secure?q={message}",
        api_method="GET",
        api_headers='{"Authorization":"Bearer secret-token","X-API-Key":"k123","Accept":"application/json"}',
        sort_order=98,
    )
    assert interface_id > 0
    iface = ApiInterfaceRepository.get_by_id(interface_id)
    payload = ApiInterfaceRepository.to_employee_payload(iface)

    assert "secret-token" not in payload["api_headers"]
    assert "k123" not in payload["api_headers"]
    assert "******" in payload["api_headers"]
    assert is_redacted_header_payload(payload["api_headers"], iface["api_headers"])
    assert "Bearer secret-token" in iface["api_headers"]
    assert "******" in redact_sensitive_headers(iface["api_headers"])


def test_restore_redacted_headers_allows_partial_edits():
    """编辑非敏感 Header 时，未修改的脱敏敏感 Header 应恢复为原值。"""
    original = '{"Authorization":"Bearer secret-token","Accept":"application/json","X-API-Key":"k123"}'
    submitted = '{"Accept":"text/plain","X-API-Key":"******","Authorization":"******","X-New":"1"}'

    restored = restore_redacted_headers(submitted, original)
    assert restored is not None
    assert "Bearer secret-token" in restored
    assert "k123" in restored
    assert "text/plain" in restored
    assert "X-New" in restored


def test_api_interface_validation_rejects_bad_input():
    """接口模板应拒绝危险 URL 和含 CRLF 的 Header。"""
    ok, reason = validate_api_url_template("file:///etc/passwd")
    assert not ok
    assert "http/https" in reason

    ok, reason = validate_api_url_template("https://example.com/a\r\nX: y")
    assert not ok
    assert "换行" in reason

    assert normalize_headers('{"X-Test":"ok"}') is not None
    assert normalize_headers('["not", "object"]') is None
    assert normalize_headers('{"X-Test":"bad\\nvalue"}') is None

    bad_id = ApiInterfaceRepository.create(
        name="_issue26_bad_",
        api_url="javascript:alert(1)",
        api_headers='{"Accept":"application/json"}',
    )
    assert bad_id == -1


def test_safe_http_rejects_private_network_urls():
    """接口测试/员工调用统一走 safe_http，发起请求前应拒绝内网地址。"""
    with pytest.raises(SafeHttpError):
        safe_http_request("http://127.0.0.1:8000/health", timeout=1)


def test_safe_http_overrides_user_supplied_host_header(monkeypatch):
    """safe_http 应移除任意大小写 Host，只发送与 URL 一致的 Host。"""
    captured = {}

    class FakeResponse:
        status = 200
        reason = "OK"

        def getheaders(self):
            return []

        def read(self, size):
            return b"{}"

    class FakeConnection:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, method, target, body=None, headers=None):
            captured["headers"] = headers

        def getresponse(self):
            return FakeResponse()

        def close(self):
            pass

    monkeypatch.setattr(safe_http_module, "validate_url_safe", lambda url: (True, "", "93.184.216.34"))
    monkeypatch.setattr(safe_http_module.http.client, "HTTPConnection", FakeConnection)

    resp = safe_http_module.safe_http_request(
        "http://example.com:8080/path",
        headers={"host": "evil.test", "HOST": "evil2.test", "X-Test": "ok"},
    )
    assert resp.status == 200
    headers = captured["headers"]
    assert headers["Host"] == "example.com:8080"
    assert [k for k in headers if str(k).lower() == "host"] == ["Host"]
    assert headers["X-Test"] == "ok"


def test_api_employee_admin_treats_http_error_as_failure(monkeypatch):
    """后台 API 型员工遇到 4xx/5xx 应返回失败，而不是 code=0。"""
    def fake_safe_http_request(*args, **kwargs):
        return SafeHttpResponse(
            status=500,
            reason="Internal Server Error",
            headers={},
            body=b"upstream failed",
            resolved_ip="93.184.216.34",
        )

    monkeypatch.setattr(admin_employee, "safe_http_request", fake_safe_http_request)
    monkeypatch.setattr(admin_employee, "write_audit_log", lambda **kwargs: None)
    monkeypatch.setattr(
        "app.utils.security.validate_url_safe",
        lambda url: (True, "", "93.184.216.34"),
    )

    class DummyHandler:
        current_user = "admin"
        request = SimpleNamespace(remote_ip="127.0.0.1")

        def __init__(self):
            self.writes = []

        def write(self, data):
            self.writes.append(data)

    dummy = DummyHandler()
    emp = {
        "id": 2601,
        "api_url": "https://example.com/api?q={message}",
        "api_method": "GET",
        "api_headers": "{}",
        "api_params_template": "",
        "api_secret": "",
    }
    asyncio.run(admin_employee.EmployeeInvokeHandler._invoke_api_employee(dummy, emp, "hello"))
    assert dummy.writes
    assert dummy.writes[-1]["code"] == 1
    assert "HTTP 500" in dummy.writes[-1]["msg"]


def test_api_employee_user_sse_treats_http_error_as_fallback(monkeypatch):
    """前台 @ API 型员工遇到 4xx/5xx 不应按成功处理，应进入远端已有 Mock 回退。"""
    def fake_safe_http_request(*args, **kwargs):
        return SafeHttpResponse(
            status=502,
            reason="Bad Gateway",
            headers={},
            body="bad gateway".encode("utf-8"),
            resolved_ip="93.184.216.34",
        )

    monkeypatch.setattr(user_chat, "safe_http_request", fake_safe_http_request)
    monkeypatch.setattr(user_chat, "write_audit_log", lambda **kwargs: None)
    monkeypatch.setattr(
        "app.utils.security.validate_url_safe",
        lambda url: (True, "", "93.184.216.34"),
    )

    class DummyHandler:
        current_user = "alice"
        request = SimpleNamespace(remote_ip="127.0.0.1")

        def __init__(self):
            self.headers = {}
            self.chunks = []

        def set_header(self, name, value):
            self.headers[name] = value

        def write(self, data):
            self.chunks.append(str(data))

        async def flush(self):
            return None

        async def _mock_api_employee_fallback(self, emp, message, start, reason):
            self.write(f"fallback:{reason}")
            await self.flush()

    dummy = DummyHandler()
    emp = {
        "id": 2602,
        "name": "接口员工",
        "api_url": "https://example.com/api?q={message}",
        "api_method": "GET",
        "api_headers": "{}",
        "api_params_template": "",
        "api_secret": "",
        "response_render_template": "",
    }
    asyncio.run(user_chat.UserEmployeeInvokeHandler._invoke_api_employee(dummy, emp, "hello"))
    output = "".join(dummy.chunks)
    assert "fallback:HTTP 502" in output


def test_api_employee_can_link_api_interface():
    """API 型数字员工应能保存接口模板关联，支持从接口库联动创建。"""
    interface_id = ApiInterfaceRepository.create(
        name="_issue26_employee_api_",
        description="员工联动测试接口",
        api_url="https://example.com/api?q={message}",
        api_method="POST",
        api_headers='{"Content-Type":"application/json"}',
        api_params_template='{"q":"{message_raw}"}',
        response_render_template='{"type":"default"}',
    )
    assert interface_id > 0
    iface = ApiInterfaceRepository.get_by_id(interface_id)

    emp_id = DigitalEmployeeRepository.create(
        name="_issue26_api_emp_",
        employee_type="api",
        description="从接口模板创建的 API 员工",
        api_url=iface["api_url"],
        api_method=iface["api_method"],
        api_headers=iface["api_headers"],
        api_params_template=iface["api_params_template"],
        response_render_template=iface["response_render_template"],
        api_interface_id=interface_id,
    )
    assert emp_id > 0

    emp = DigitalEmployeeRepository.get_by_id(emp_id)
    assert emp["employee_type"] == "api"
    assert emp["api_interface_id"] == interface_id
    assert emp["api_url"] == iface["api_url"]
    assert emp["api_method"] == "POST"


def test_delete_interface_clears_employee_reference():
    """删除接口模板前应显式清空员工关联，兼容旧库缺少 FK 的场景。"""
    interface_id = ApiInterfaceRepository.create(
        name="_issue26_delete_ref_",
        description="删除清理关联测试",
        api_url="https://example.com/delete-ref?q={message}",
        api_method="GET",
        api_headers='{"Accept":"application/json"}',
    )
    assert interface_id > 0
    emp_id = DigitalEmployeeRepository.create(
        name="_issue26_api_emp_delete_ref_",
        employee_type="api",
        api_url="https://example.com/delete-ref?q={message}",
        api_method="GET",
        api_headers='{"Accept":"application/json"}',
        api_interface_id=interface_id,
    )
    assert emp_id > 0

    assert ApiInterfaceRepository.delete(interface_id)
    emp = DigitalEmployeeRepository.get_by_id(emp_id)
    assert emp is not None
    assert emp["api_interface_id"] is None


if __name__ == "__main__":
    setup_module()
    try:
        test_api_interface_crud_and_employee_payload()
        test_sensitive_headers_are_redacted_in_employee_payload()
        test_restore_redacted_headers_allows_partial_edits()
        test_api_interface_validation_rejects_bad_input()
        test_safe_http_rejects_private_network_urls()
        test_api_employee_can_link_api_interface()
        test_delete_interface_clears_employee_reference()
        print("Issue #26 接口管理测试通过")
    finally:
        teardown_module()
