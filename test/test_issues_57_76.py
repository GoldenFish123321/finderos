import os
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.controllers.auth import LoginRateLimiter
from app.controllers import user_chat
from app.controllers.admin_interface import _execute_interface_sync
from app.controllers.admin_model import ModelQuickConfigHandler
from app.controllers.admin_user import _reserve_password_attempt, _pwd_change_attempts
from app.models.ai_model import AiModelRepository
import app.models.db as db_module
from app.services.collector import _decompress


ROOT = os.path.dirname(os.path.dirname(__file__))


def _read(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as handle:
        return handle.read()


def test_issue_57_mock_uses_model_prompt_status():
    source = _read("app/controllers/user_chat.py")
    body = source[source.index("async def _mock_chat_response"):]
    body = body[:body.index("class UserEmployeeInvokeHandler")]
    assert "model.get('system_prompt')" in body
    assert "if system_prompt else" not in body


def test_issues_59_61_67_input_boundaries_are_present():
    registry = _read("app/mcp/registry.py")
    chat = _read("app/controllers/user_chat.py")
    assert 'urllib.parse.quote(str(value), safe="")' in registry
    assert 'result_data.get("source"' in chat
    assert "sanitize_untrusted_llm_context(" in chat
    assert ".strip()[:200]" in chat


def test_issue_60_stale_tts_locks_are_cleaned(tmp_path, monkeypatch):
    stale = tmp_path / "old.mp3.lock"
    fresh = tmp_path / "new.mp3.lock"
    stale.write_text("", encoding="ascii")
    fresh.write_text("", encoding="ascii")
    os.utime(stale, (time.time() - 1000, time.time() - 1000))
    monkeypatch.setattr(user_chat, "_TTS_CACHE_DIR", str(tmp_path))
    assert user_chat._cleanup_stale_tts_locks(300) == 1
    assert not stale.exists()
    assert fresh.exists()


def test_issues_62_70_rate_limiter_is_thread_safe(monkeypatch):
    limiter = LoginRateLimiter("test")
    monkeypatch.setattr("app.controllers.auth.settings.LOGIN_MAX_FAILURES", 1000)
    workers = [threading.Thread(target=limiter.record_failure, args=("ip", "user")) for _ in range(50)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    assert limiter._failures[("ip", "user")][0] == 50
    assert hasattr(limiter, "_lock")


def test_issue_62_registration_limiter_runs_on_post_only():
    source = _read("app/controllers/auth.py")
    register = source[source.index("class RegisterHandler"):]
    get_body, post_body = register.split("    def post(self):", 1)
    assert "register_limiter.check" not in get_body
    assert "register_limiter.check" in post_body
    assert "client_ip = self.request.remote_ip" in post_body


def test_issues_63_68_password_change_output_is_safe():
    source = _read("app/controllers/admin_user.py")
    assert "_pwd_change_lock = threading.RLock()" in source
    assert 'alert("{msg}' not in source
    assert "xhtml_escape(msg)" in source


def test_issue_63_password_attempt_reservation_is_atomic():
    key = "pwd:concurrent-test"
    _pwd_change_attempts.pop(key, None)
    results = []
    workers = [threading.Thread(target=lambda: results.append(_reserve_password_attempt(key, time.time()))) for _ in range(20)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    assert sum(results) == 5
    _pwd_change_attempts.pop(key, None)


def test_issues_64_66_fts_queries_escape_quotes():
    source = _read("app/models/data_warehouse.py")
    tool_source = _read("app/mcp/builtin_tools/warehouse_tools.py")
    assert "replace(chr(34), chr(34) * 2)" in source
    assert "replace('\"', '\"\"')" in tool_source


def test_issues_69_71_url_templates_are_rejected_early():
    scheduler = _read("app/services/scheduler.py")
    controller = _read("app/controllers/admin_watch_source.py")
    assert 'if "{" in request_url or "}" in request_url' in scheduler
    assert '{"http", "https"}' in controller


def test_issue_72_random_admin_password_not_logged():
    source = _read("app/models/db.py")
    assert "一次性随机密码: {initial_password}" not in source


def test_issue_72_stale_bootstrap_sidecar_is_replaced(tmp_path, monkeypatch):
    database = tmp_path / "fresh.db"
    sidecar = tmp_path / "fresh.db.admin_initial_password"
    sidecar.write_text("stale\n", encoding="utf-8")
    monkeypatch.setattr(db_module, "DB_PATH", str(database))
    monkeypatch.setattr("app.models.db.settings.ADMIN_DEFAULT_PASSWORD", "")
    db_module.init_db()
    db_module.seed_default_data()
    password = sidecar.read_text(encoding="utf-8").strip()
    assert password and password != "stale"


def test_issue_73_api_keys_are_opt_in(monkeypatch):
    decrypt_calls = []
    monkeypatch.setattr("app.models.ai_model.decrypt_api_key", lambda value: decrypt_calls.append(value) or "plain")
    rows, _ = AiModelRepository.get_all(page=1, page_size=1)
    assert rows and rows[0]["api_key"] == ""
    assert decrypt_calls == []
    row = AiModelRepository.get_by_id(rows[0]["id"], include_api_key=True)
    assert row["api_key"] == "plain"
    assert len(decrypt_calls) == 1


def test_model_quick_config_falls_back_when_no_default():
    handler = SimpleNamespace(
        current_user="alice",
        get_query_argument=lambda name, default="": default,
    )
    handler._get_user_models = lambda include_api_key=True: AiModelRepository.get_all(
        page=1, page_size=1, include_api_key=include_api_key,
        model_scope="user", owner_username=handler.current_user,
    )[0]
    with patch.object(AiModelRepository, "get_default", return_value=None), \
         patch.object(AiModelRepository, "get_all", return_value=([{"id": 9}], 1)):
        assert ModelQuickConfigHandler._get_target_model(handler) == {"id": 9}


def test_issue_65_interface_response_secrets_are_redacted():
    response = SimpleNamespace(
        status=200,
        reason="OK",
        headers={"Content-Type": "application/json", "Set-Cookie": "sid=secret"},
        body=b'{"client_secret":"secret","id_token":"jwt","value":1}',
    )
    interface = {"api_url": "https://example.test/api", "api_method": "GET"}
    with patch("app.controllers.admin_interface.validate_url_safe", return_value=(True, "", "93.184.216.34")), \
         patch("app.controllers.admin_interface.safe_http_request", return_value=response):
        result = _execute_interface_sync(interface, "hello")
    assert result["headers"]["Set-Cookie"] == "[REDACTED]"
    assert result["data"]["client_secret"] == "[REDACTED]"
    assert result["data"]["id_token"] == "[REDACTED]"

    response.body = b"access_token=secret-token&value=1"
    with patch("app.controllers.admin_interface.validate_url_safe", return_value=(True, "", "93.184.216.34")), \
         patch("app.controllers.admin_interface.safe_http_request", return_value=response):
        text_result = _execute_interface_sync(interface, "hello")
    assert "secret-token" not in text_result["raw"]


def test_issues_74_76_template_boundaries():
    form = _read("app/templates/admin/employee_form.html")
    employee_list = _read("app/templates/admin/employee_list.html")
    base = _read("app/static/js/base.js")
    assert "data-headers='{{" in form
    assert "escapeHtml(name)" in employee_list
    assert "replace('{name}', escapeHtml(name))" in base


def test_issue_58_valid_brotli_is_decompressed():
    brotli = pytest.importorskip("brotli")
    payload = b"finderos-brotli"
    assert _decompress(brotli.compress(payload), "br") == payload


def test_issue_58_oversized_brotli_is_rejected():
    brotli = pytest.importorskip("brotli")
    compressed = brotli.compress(b"x" * (30 * 1024 * 1024 + 1))
    with pytest.raises(ValueError, match="超过大小限制"):
        _decompress(compressed, "br")


def test_employee_invoke_passes_tools_to_llm():
    """验证 @员工 LLM 调用传了 tools 参数，使 load_skill 等工具可用。

    修复前：_invoke_llm_employee 的流式调用缺少 tools 参数，
    导致 LLM 无法通过 Function Calling 调用 load_skill。
    修复后：Phase 1 非流式轮次传 tools，Phase 2 流式不传 tools。
    """
    src = _read("app/controllers/user_chat.py")
    body = src[src.index("async def _invoke_llm_employee"):]
    body = body[:body.index("async def _mock_employee_response")]

    # Phase 1 非流式调用必须包含 tools
    assert "get_openai_tools_for_employee" in body, (
        "应调用 get_openai_tools_for_employee 获取员工权限过滤后的工具列表"
    )
    assert '"tools": emp_tools' in body or '"tools":' in body, (
        "Phase 1 非流式调用必须传 tools 参数"
    )
    assert '"tool_choice": "auto"' in body, (
        "Phase 1 应设置 tool_choice: auto"
    )
    assert '"stream": False' in body, (
        "Phase 1 工具调用轮次应为非流式"
    )

    # Phase 2 流式调用不应包含 tools（保证流畅输出）
    # 检查最后的流式调用
    phase2_section = body[body.rindex('"stream": True'):]
    assert '"tools"' not in phase2_section.split('"stream": True')[1][:500], (
        "Phase 2 流式调用不应传 tools（保证输出流畅）"
    )
