"""Issue #160: every user-facing password change uses one strong policy."""

from pathlib import Path

import pytest

import app.models.db as db_module
from app.models.db import init_db, seed_default_data
from app.models.user import UserRepository


ROOT = Path(__file__).resolve().parents[1]


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DB_PATH", str(tmp_path / "issue160.db"))
    init_db()
    seed_default_data()


def test_repository_rejects_weak_password_and_accepts_shared_policy(isolated_db):
    assert UserRepository.create_user("issue160", "OldPassword9", role_id=2)
    user = UserRepository.get_user_by_username("issue160")

    ok, message = UserRepository.update_password(user["id"], "OldPassword9", "123456")
    assert not ok
    assert "至少需要8个字符" in message
    assert UserRepository.verify_user("issue160", "OldPassword9")

    ok, message = UserRepository.update_password(
        user["id"], "OldPassword9", "NewPassword8"
    )
    assert ok, message
    assert UserRepository.verify_user("issue160", "NewPassword8")


def test_all_web_password_entry_points_use_the_shared_policy():
    admin_user = read("app/controllers/admin_user.py")
    auth = read("app/controllers/auth.py")

    assert "validate_password_strength(password)" in admin_user
    assert auth.count("validate_password_strength(") >= 2
    assert "validate_password_strength(new_password)" in auth


def test_password_templates_show_the_same_requirements():
    templates = [
        read("app/templates/register.html"),
        read("app/templates/admin/change_password.html"),
        read("app/templates/admin/user_form.html"),
        read("app/templates/user_account.html"),
    ]

    for template in templates:
        assert "至少8" in template
        assert "minlength=\"8\"" in template
        assert "至少6" not in template


def test_admin_cli_checks_character_categories_too():
    source = read("make_admin.py")
    assert "len(password) < 8" in source
    assert "validate_password_strength(password)" in source
