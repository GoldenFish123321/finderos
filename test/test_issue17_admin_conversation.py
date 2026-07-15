"""
Issue #17: 管理侧会话管理

覆盖：
- ConversationRepository 管理侧跨用户分页/筛选
- 用户侧 get_all 默认仍按 username 隔离
- 消息详情读取与删除级联
- 管理路由与模板注册
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


def _reset_conversations():
    with db_module.get_db() as conn:
        conn.execute("DELETE FROM conversation_messages")
        conn.execute("DELETE FROM conversations")
        conn.execute("DELETE FROM audit_logs WHERE action = ?", ("ADMIN_CONVERSATION_DELETE",))
        conn.commit()


def _seed_conversations():
    from app.models.conversation import ConversationRepository

    _reset_conversations()
    alice = ConversationRepository.create("Alice 会话", username="alice")
    bob = ConversationRepository.create("Bob 项目讨论", username="bob")
    ConversationRepository.add_message(alice, "user", "你好", 1)
    ConversationRepository.add_message(alice, "assistant", "你好，我能帮你什么？", 6)
    ConversationRepository.add_message(bob, "user", "项目进度如何？", 3)
    return alice, bob


def _reset_permissions():
    with db_module.get_db() as conn:
        conn.execute("DELETE FROM role_functions")
        conn.execute("DELETE FROM users WHERE username LIKE ?", ("_issue17_perm_%",))
        conn.execute("DELETE FROM roles WHERE name LIKE ?", ("_issue17_perm_%",))
        conn.execute("DELETE FROM functions WHERE route_path IN (?, ?)", ("/admin/model", "/admin/conversation"))
        conn.commit()


def test_admin_get_all_cross_user_and_filters():
    from app.models.conversation import ConversationRepository

    alice, bob = _seed_conversations()
    rows, total = ConversationRepository.get_all_admin(page=1, page_size=20)
    assert total == 2
    assert {r["username"] for r in rows} == {"alice", "bob"}
    assert {r["msg_count"] for r in rows} == {1, 2}

    rows, total = ConversationRepository.get_all_admin(username="alice")
    assert total == 1
    assert rows[0]["id"] == alice
    assert rows[0]["msg_count"] == 2

    rows, total = ConversationRepository.get_all_admin(keyword="项目")
    assert total == 1
    assert rows[0]["id"] == bob


def test_user_get_all_still_scoped_by_username():
    from app.models.conversation import ConversationRepository

    _seed_conversations()
    alice_rows = ConversationRepository.get_all(username="alice")
    assert len(alice_rows) == 1
    assert alice_rows[0]["username"] == "alice"

    all_rows = ConversationRepository.get_all(include_all=True)
    assert len(all_rows) == 2


def test_messages_detail_and_delete_cascade():
    from app.models.conversation import ConversationRepository

    alice, _ = _seed_conversations()
    messages = ConversationRepository.get_messages(alice, limit=20)
    assert [m["role"] for m in messages] == ["user", "assistant"]

    assert ConversationRepository.delete(alice)
    assert ConversationRepository.get_by_id(alice) is None
    assert ConversationRepository.get_messages(alice, limit=20) == []


def test_admin_conversation_routes_and_template():
    from main import make_app
    from tornado.template import Loader

    app = make_app()
    patterns = [rule.matcher.regex.pattern for rule in app.wildcard_router.rules]
    assert any("/admin/conversation" in p for p in patterns)
    assert any("/admin/conversation/delete" in p for p in patterns)

    loader = Loader("app/templates")
    loader.load("admin/conversation_list.html")


def test_admin_delete_handler_has_audit_log():
    from pathlib import Path

    source = Path("app/controllers/admin_conversation.py").read_text(encoding="utf-8")
    assert "ADMIN_CONVERSATION_DELETE" in source
    assert "ConversationRepository.delete" in source


def test_conversation_permission_requires_function_node():
    from app.controllers.admin_conversation import _has_conversation_manage_permission

    _reset_permissions()
    with db_module.get_db() as conn:
        conn.execute("INSERT INTO roles (id, name, description) VALUES (?, ?, ?)", (501, "_issue17_perm_role_", "测试角色"))
        conn.execute(
            "INSERT INTO users (username, password_hash, salt, role_id, is_enabled) VALUES (?, ?, ?, ?, ?)",
            ("_issue17_perm_user_", "hash", "00", 501, 1),
        )
        conn.execute(
            "INSERT INTO functions (id, name, route_path, is_enabled) VALUES (?, ?, ?, ?)",
            (501, "模型引擎", "/admin/model", 1),
        )
        conn.execute("INSERT INTO role_functions (role_id, function_id) VALUES (?, ?)", (501, 501))
        conn.commit()

    assert _has_conversation_manage_permission("_issue17_perm_user_") is False

    with db_module.get_db() as conn:
        conn.execute(
            "INSERT INTO functions (id, name, route_path, is_enabled) VALUES (?, ?, ?, ?)",
            (502, "会话管理", "/admin/conversation", 1),
        )
        conn.execute("INSERT INTO role_functions (role_id, function_id) VALUES (?, ?)", (501, 502))
        conn.commit()

    assert _has_conversation_manage_permission("_issue17_perm_user_") is True


def test_delete_confirm_does_not_embed_user_title():
    from pathlib import Path

    template = Path("app/templates/admin/conversation_list.html").read_text(encoding="utf-8")
    assert "data-title" not in template
    assert "确认删除「" not in template
    assert "确认删除该会话" in template
