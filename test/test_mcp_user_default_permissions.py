"""
MCP 工具管理说明与普通用户默认权限。

覆盖：
- 普通用户角色默认获得 /admin/model/config，用于配置模型 API
- 后台路由权限按功能路由精确/最长前缀匹配
- MCP 工具管理页提供可操作的使用说明
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app.config.settings as settings
import app.models.db as db_module


TEST_DB_PATH = None
_ORIGINAL_SETTINGS_DB_PATH = settings.settings.DB_PATH
_ORIGINAL_MODULE_DB_PATH = getattr(settings, "DB_PATH", None)
_ORIGINAL_DB_MODULE_DB_PATH = db_module.DB_PATH


def setup_module():
    global TEST_DB_PATH
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    TEST_DB_PATH = tmp.name
    tmp.close()

    settings.DB_PATH = TEST_DB_PATH
    settings.settings.DB_PATH = TEST_DB_PATH
    db_module.DB_PATH = TEST_DB_PATH
    db_module.init_db()
    db_module.seed_default_data()


def teardown_module():
    if _ORIGINAL_MODULE_DB_PATH is None:
        try:
            delattr(settings, "DB_PATH")
        except AttributeError:
            pass
    else:
        settings.DB_PATH = _ORIGINAL_MODULE_DB_PATH
    settings.settings.DB_PATH = _ORIGINAL_SETTINGS_DB_PATH
    db_module.DB_PATH = _ORIGINAL_DB_MODULE_DB_PATH

    if TEST_DB_PATH and os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)


def test_normal_user_gets_model_api_permission_by_default():
    from app.models.user import UserRepository

    assert UserRepository.create_user("_mcp_perm_user_", "test123456", role_id=2)

    routes = UserRepository.get_user_function_routes("_mcp_perm_user_")
    assert routes[0] == "/admin/model/config"
    assert "/admin/model/config" in routes
    assert "/admin" not in routes
    assert "/admin/model" not in routes
    assert "/admin/mcp/tool" not in set(routes)


def test_admin_route_permission_resolves_specific_routes():
    from app.controllers.admin_base import AdminBaseHandler

    handler = object.__new__(AdminBaseHandler)
    assert handler._resolve_required_route("/admin") == "/admin"
    assert handler._resolve_required_route("/admin/model/config") == "/admin/model/config"
    assert handler._resolve_required_route("/admin/model/config/test") == "/admin/model/config"
    assert handler._resolve_required_route("/admin/model/add") == "/admin/model"
    assert handler._resolve_required_route("/admin/api/model/list") == "/admin/model"
    assert handler._resolve_required_route("/admin/mcp/reload") == "/admin/mcp/tool"
    # 最长前缀优先，采集日志不应被宽泛的 /admin/watch 误放行。
    assert handler._resolve_required_route("/admin/watch/log") == "/admin/watch/log"


def test_disabled_specific_route_does_not_fall_back_to_parent():
    from app.controllers.admin_base import AdminBaseHandler

    with db_module.get_db() as conn:
        conn.execute("UPDATE functions SET is_enabled = 0 WHERE route_path = ?", ("/admin/watch/log",))
        conn.commit()
    try:
        handler = object.__new__(AdminBaseHandler)
        assert handler._resolve_required_route("/admin/watch/log") == "/admin/watch/log"
    finally:
        with db_module.get_db() as conn:
            conn.execute("UPDATE functions SET is_enabled = 1 WHERE route_path = ?", ("/admin/watch/log",))
            conn.commit()


def test_mcp_pages_explain_how_to_use_tools():
    from pathlib import Path

    list_template = Path("app/templates/admin/mcp_tool_list.html").read_text(encoding="utf-8")
    form_template = Path("app/templates/admin/mcp_tool_form.html").read_text(encoding="utf-8")
    employee_template = Path("app/templates/admin/employee_form.html").read_text(encoding="utf-8")

    assert "怎么判断 MCP 工具能不能用" in list_template
    assert "热重载" in list_template
    assert "数字员工 → 编辑 → MCP 工具权限" in list_template
    assert "https://api.example.com/weather?city={city}" in form_template
    assert 'href="/admin/mcp/tool"' in employee_template


def test_model_quick_config_route_and_template():
    from main import make_app
    from tornado.template import Loader

    app = make_app()
    patterns = [rule.matcher.regex.pattern for rule in app.wildcard_router.rules]
    assert any("/admin/model/config" in p for p in patterns)
    assert any("/admin/model/config/test" in p for p in patterns)

    template = Loader("app/templates").load("admin/model_quick_config.html")
    assert template is not None


def test_chat_page_exposes_model_api_config_link():
    from pathlib import Path
    from tornado.template import Loader

    template = Path("app/templates/user_chat.html").read_text(encoding="utf-8")
    controller = Path("app/controllers/user_chat.py").read_text(encoding="utf-8")
    Loader("app/templates").load("user_chat.html")

    assert 'href="/admin/model/config"' in template
    assert "配置模型 API" in template
    assert "model-config-link" in template
    assert "quick-action quick-action-link" in template
    assert "{% if can_config_model_api %}" in template
    assert "can_config_model_api" in controller
    assert "UserRepository.get_user_function_routes" in controller


def test_model_quick_config_detects_endpoint_change():
    from app.controllers.admin_model import (
        _model_connection_changed,
        _resolve_quick_config_api_key,
    )

    model = {
        "provider": "openai",
        "api_base": "https://api.openai.com/v1",
        "model_name": "gpt-4o-mini",
        "api_key": "sk-saved",
    }
    assert not _model_connection_changed(
        model, "openai", "https://api.openai.com/v1", "gpt-4o-mini"
    )
    assert _model_connection_changed(
        model, "openai", "https://example.invalid/v1", "gpt-4o-mini"
    )
    assert _model_connection_changed(
        model, "deepseek", "https://api.openai.com/v1", "gpt-4o-mini"
    )
    assert _model_connection_changed(
        model, "openai", "https://api.openai.com/v1", "gpt-4o"
    )
    assert _resolve_quick_config_api_key(
        model, "openai", "https://api.openai.com/v1", "gpt-4o-mini", ""
    ) == ("sk-saved", "")
    assert _resolve_quick_config_api_key(
        model, "openai", "https://example.invalid/v1", "gpt-4o-mini", ""
    )[1]
    assert _resolve_quick_config_api_key(
        model, "openai", "https://example.invalid/v1", "gpt-4o-mini", "sk-saved"
    )[1]
    assert _resolve_quick_config_api_key(
        model,
        "openai",
        "https://example.invalid/v1",
        "gpt-4o-mini",
        "sk-saved",
        confirm_reuse_key=True,
    ) == ("sk-saved", "")
    assert _resolve_quick_config_api_key(
        model, "openai", "https://example.invalid/v1", "gpt-4o-mini", "sk-new"
    ) == ("sk-new", "")


def test_model_quick_config_template_key_echo_and_test_ui():
    from pathlib import Path
    from tornado.template import Loader

    source = Path("app/templates/admin/model_quick_config.html").read_text(encoding="utf-8")
    Loader("app/templates").load("admin/model_quick_config.html")
    assert 'id="api-key-input"' in source
    assert 'value="{{ model[\'api_key\'] if model else \'\' }}"' in source
    assert "toggle-api-key" in source
    assert "已保存密钥" in source
    assert "user-model-switch" in source
    assert "只管理“我的模型配置”分组" in source
    assert "新建我的模型" in source
    assert "设为我的默认模型" in source
    assert "api-key-reuse-confirm" in source
    assert "confirm_reuse_key" in source
    assert 'id="confirm-reuse-key"' in source
    assert 'lay-filter="quick-provider"' in source
    assert "clearKeySelected()" in source
    assert "select(quick-provider)" in source
    assert "连接信息已变更" in source
    assert "connectionChanged()" in source
    assert "requireReuseConfirm" in source
    assert "我确认将当前已保存密钥用于新的提供商" in source
    assert "测试连接" in source
    assert "/admin/model/config/test" in source


def test_model_quick_config_handlers_use_confirm_reuse_flag():
    from pathlib import Path

    source = Path("app/controllers/admin_model.py").read_text(encoding="utf-8")
    save_handler = source[
        source.index("class ModelQuickConfigHandler"):
        source.index("class ModelQuickConfigTestHandler")
    ]
    test_handler = source[
        source.index("class ModelQuickConfigTestHandler"):
        source.index("class ModelDeleteHandler")
    ]

    for handler_source in (save_handler, test_handler):
        assert 'confirm_reuse_key = self.get_body_argument("confirm_reuse_key", "0") == "1"' in handler_source
        assert "clear_key, confirm_reuse_key" in handler_source
        assert "_get_target_model" in handler_source
    assert "owner_username" in save_handler
    assert 'model_scope="user"' in save_handler


def test_model_quick_config_test_redacts_key_and_reports_success():
    from app.controllers.admin_model import (
        _redact_model_test_text,
        _test_model_connection_sync,
    )
    from app.utils.safe_http import SafeHttpResponse
    from unittest.mock import patch

    assert "sk-secret" not in _redact_model_test_text("bad sk-secret", "sk-secret")

    response = SafeHttpResponse(
        status=200,
        reason="OK",
        headers={},
        body=b'{"choices":[{"message":{"content":"ok"}}]}',
        resolved_ip="93.184.216.34",
    )
    with patch("app.controllers.admin_model.safe_http_request", return_value=response) as req:
        result = _test_model_connection_sync(
            "openai",
            "https://api.example.test/v1",
            "sk-secret",
            "gpt-test",
        )
    assert result["code"] == 0
    assert "测试成功" in result["msg"]
    assert "sk-secret" not in result["msg"]
    call_kwargs = req.call_args.kwargs
    assert call_kwargs["method"] == "POST"
    assert call_kwargs["headers"]["Authorization"] == "Bearer sk-secret"


def test_login_and_index_default_to_chat():
    from pathlib import Path

    auth_source = Path("app/controllers/auth.py").read_text(encoding="utf-8")
    home_source = Path("app/controllers/home.py").read_text(encoding="utf-8")
    redirect_body = auth_source[auth_source.index("def _redirect_by_role"):]
    redirect_body = redirect_body[:redirect_body.index("class LogoutHandler")]
    assert 'self.redirect("/chat")' in redirect_body
    assert 'routes = [r for r in UserRepository.get_user_function_routes' not in redirect_body
    assert 'self.redirect("/chat")' in home_source


def test_mcp_registry_rebinds_to_new_server():
    from app.mcp.registry import MCPToolRegistry
    from app.mcp.server import MCPServer
    from app.mcp.tools import register_all_tools

    MCPToolRegistry._instance = None
    server_a = MCPServer()
    register_all_tools(server_a)
    assert server_a.tool_count > 0

    server_b = MCPServer()
    register_all_tools(server_b)
    assert server_b.tool_count > 0
    assert MCPToolRegistry.get_instance()._server is server_b
