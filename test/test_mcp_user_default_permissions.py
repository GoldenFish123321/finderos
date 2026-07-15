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

    template = Loader("app/templates").load("admin/model_quick_config.html")
    assert template is not None


def test_model_quick_config_detects_endpoint_change():
    from app.controllers.admin_model import _model_connection_changed

    model = {
        "provider": "openai",
        "api_base": "https://api.openai.com/v1",
        "model_name": "gpt-4o-mini",
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
