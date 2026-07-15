"""Shared pytest isolation for legacy tests that otherwise use the live DB path."""
import os
import shutil
import tempfile
import uuid

import pytest

from app.config.settings import settings
import app.models.db as db_module


_ISOLATED_MODULES = {
    "test_bug32_employee_ui_display",
    "test_issue17_admin_conversation",
    "test_issue24_collect_progress",
    "test_mcp_refactor",
    "test_skill",
    "test_user_models",
    "test_v0_3_enhancements",
}


@pytest.fixture(scope="session", autouse=True)
def _legacy_suite_database():
    original_setting = settings.DB_PATH
    original_module = db_module.DB_PATH
    tmpdir = tempfile.TemporaryDirectory(prefix="finderos-pytest-")
    template_db = os.path.join(tmpdir.name, "template.db")
    settings.DB_PATH = template_db
    db_module.DB_PATH = template_db
    db_module.init_db()
    db_module.seed_default_data()
    yield {"dir": tmpdir.name, "template": template_db,
           "original_setting": original_setting, "original_module": original_module}
    settings.DB_PATH = original_setting
    db_module.DB_PATH = original_module
    tmpdir.cleanup()


@pytest.fixture(autouse=True)
def _route_legacy_test_to_suite_db(request, _legacy_suite_database):
    module_name = request.module.__name__.split(".")[-1]
    if module_name in _ISOLATED_MODULES:
        yield
        return

    test_db = os.path.join(_legacy_suite_database["dir"], f"test-{uuid.uuid4().hex}.db")
    shutil.copy2(_legacy_suite_database["template"], test_db)
    settings.DB_PATH = test_db
    db_module.DB_PATH = test_db
    try:
        yield
    finally:
        settings.DB_PATH = _legacy_suite_database["template"]
        db_module.DB_PATH = _legacy_suite_database["template"]
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(test_db + suffix)
            except FileNotFoundError:
                pass
