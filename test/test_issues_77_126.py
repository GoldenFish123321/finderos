import os
import ast
import logging
import sqlite3
import zipfile
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.config.settings import Settings
from app.controllers.admin_config import validate_config_updates
from app.controllers.user_chat import _build_employee_card, _build_weather_card
from app.models import db as db_module
from app.models.system_config import SystemConfigRepository
from app.services.media_generator import ImageGenHandler, _VIDEO_CACHE_DIR
from app.services.system_operations import backup_database_if_due
from migrate_db import _column_exists


ROOT = os.path.dirname(os.path.dirname(__file__))


def read(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as handle:
        return handle.read()


def test_config_logo_transaction_and_feedback_boundaries():
    controller = read("app/controllers/admin_config.py")
    template = read("app/templates/admin/config.html")
    assert controller.index("updates = {}") < controller.index('updates["system_logo"] = ""')
    assert controller.index("SystemConfigRepository.bulk_update") < controller.index("_cleanup_old_logos(logo_filename)")
    assert "logger.error(" in controller
    assert "data-msg=\"{{ feedback_msg }}\"" in template
    assert "layer.msg('{{ feedback_msg }}'" not in template


def test_settings_ranges_and_extended_whitelist(monkeypatch):
    values = {
        "ai_default_temperature": "99", "ai_default_max_tokens": "0",
        "default_port": "12000", "registration_enabled": "false",
    }
    instance = Settings()
    original_temp = instance.AI_DEFAULT_TEMPERATURE
    with patch("app.models.system_config.SystemConfigRepository.get_all_as_dict", return_value=values):
        instance.load_from_db()
    assert instance.AI_DEFAULT_TEMPERATURE == original_temp
    assert instance.AI_DEFAULT_MAX_TOKENS == 4096
    assert instance.PORT == 12000
    assert instance.REGISTRATION_ENABLED is False

    monkeypatch.setenv("PORT", "13000")
    instance.PORT = 13000
    with patch("app.models.system_config.SystemConfigRepository.get_all_as_dict", return_value={"default_port": "12000"}):
        instance.load_from_db()
    assert instance.PORT == 13000


def test_existing_database_gets_new_config_keys_and_persists_them(tmp_path, monkeypatch):
    database = tmp_path / "upgrade.db"
    old_keys = (
        "system_name", "system_subtitle", "system_logo", "icp_number",
        "default_port", "ai_default_model", "ai_default_temperature",
        "ai_default_max_tokens",
    )
    with sqlite3.connect(database) as conn:
        conn.execute(
            "CREATE TABLE system_config ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT UNIQUE NOT NULL, "
            "value TEXT DEFAULT '', description TEXT DEFAULT '', "
            "category TEXT DEFAULT 'general', "
            "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        conn.executemany(
            "INSERT INTO system_config (key, value) VALUES (?, ?)",
            [(key, "legacy") for key in old_keys],
        )
    monkeypatch.setattr(db_module, "DB_PATH", str(database))
    db_module.init_db()
    db_module.seed_default_data()
    configs = SystemConfigRepository.get_all_as_dict()
    assert len(configs) >= 19
    assert configs["system_name"] == "legacy"
    assert SystemConfigRepository.update("db_backup_path", "custom/backups")
    assert SystemConfigRepository.get_by_key("db_backup_path")["value"] == "custom/backups"


def test_system_config_rejects_invalid_persisted_values():
    validate_config_updates({"default_port": "65535", "log_level": "warning"})
    for updates in (
        {"default_port": "0"}, {"upload_max_size_mb": "unlimited"},
        {"ai_default_temperature": "2.1"}, {"log_level": "TRACE"},
        {"webhook_url": "file:///tmp/a"},
    ):
        with pytest.raises(ValueError):
            validate_config_updates(updates)


def test_sentiment_scanner_can_restart_after_stop():
    from app.services.scheduler import SentimentScanner
    scanner = SentimentScanner()
    scanner.start()
    scanner.stop()
    scanner.start()
    scanner.stop()


def test_collection_scheduler_can_restart_after_stop():
    from app.services.scheduler import CollectionScheduler
    scheduler = CollectionScheduler(None)
    scheduler.start()
    scheduler.stop()
    scheduler.start()
    scheduler.stop()


def test_media_generation_uses_safe_http_and_generic_errors():
    response = SimpleNamespace(status=401, reason="Unauthorized", body=b'{"error":{"message":"provider secret detail"}}', headers={})
    with patch("app.services.media_generator.validate_url_safe", return_value=(True, "", "93.184.216.34")), \
         patch("app.services.media_generator.safe_http_request", return_value=response):
        result = ImageGenHandler.generate_image("prompt", "model", "https://example.test/v1", "key")
    assert result == {"success": False, "error": "媒体生成服务请求失败"}
    assert os.path.isabs(_VIDEO_CACHE_DIR)
    assert "urllib.request.urlopen" not in read("app/services/media_generator.py")


def test_weather_card_preserves_chinese_city_and_conditions():
    card = _build_weather_card(
        {"city": "成都", "weather": {"temperature": "23", "condition": "晴"}},
        "天气", "成都今天天气",
    )
    assert card["type"] == "weather"
    assert card["data"]["city"] == "成都"
    assert card["data"]["weather"] == "晴"


def test_non_weather_json_is_not_misclassified():
    card = _build_employee_card(
        {"name": "普通接口", "employee_type": "api", "response_render_template": ""},
        {"template": "hello"},
    )
    assert card is None


def test_password_policy_and_migration_identifier_validation():
    from app.utils.security import validate_password_strength
    assert not validate_password_strength("short7")[0]
    assert validate_password_strength("LongPass123!")[0]
    assert "len(password) < 8" in read("make_admin.py")
    assert "密码至少需要6个字符" not in read("app/controllers/auth.py")
    assert "新密码长度不能少于6个字符" not in read("app/controllers/admin_user.py")
    assert "cryptography>=43.0" in read("requirements.txt")
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE valid_table (id INTEGER)")
    assert _column_exists(conn, "valid_table", "id")
    with pytest.raises(ValueError):
        _column_exists(conn, 'valid_table); DROP TABLE valid_table;--', "id")


def test_gitignore_entry_is_utf8_and_effective():
    data = open(os.path.join(ROOT, ".gitignore"), "rb").read()
    assert b"\x00" not in data
    assert b"rewrite_commits.py" in data


def test_frontend_cleanup_mobile_and_error_feedback():
    chat = read("app/templates/user_chat.html")
    dashboard = read("app/templates/admin/dashboard.html")
    sentiment = read("app/templates/admin/sentiment.html")
    assert "node._resizeObserver.disconnect()" in chat
    assert "showRequestError" in chat
    assert "position: fixed; left: 0; right: 0; bottom: 0" in chat
    assert "totalFreq" not in dashboard
    assert "triggerScan(this)" in sentiment
    assert ".catch(function()" in sentiment
    assert "\\\\'图片加载失败" not in chat
    assert "\\\\'none" not in chat


def test_async_chat_paths_and_card_logging():
    source = read("app/controllers/user_chat.py")
    assert "await loop.run_in_executor" in source
    assert "_read_binary_file(cache_file)" in source
    assert "Failed to render music tool card" in source
    assert "Failed to render follow-up tool card" in source


def test_mcp_tools_has_no_bom_and_parses_as_utf8():
    source = read("app/mcp/tools.py")
    assert not source.startswith("\ufeff")
    ast.parse(source)


@pytest.mark.parametrize("module_name", ["collector", "deep_collector"])
@pytest.mark.parametrize(
    ("encoding", "expected_messages"),
    [
        ("gzip", ("gzip 响应解压失败",)),
        ("deflate", ("zlib deflate 解压失败", "raw deflate 解压失败")),
    ],
)
def test_collector_decompression_fallbacks_are_logged(
    caplog, module_name, encoding, expected_messages
):
    from app.services import collector, deep_collector

    module = {"collector": collector, "deep_collector": deep_collector}[module_name]
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger=module.__name__):
        assert module._decompress(b"invalid-compressed-data", encoding) == b"invalid-compressed-data"

    messages = [
        record.getMessage()
        for record in caplog.records
        if record.name == module.__name__
    ]
    for expected in expected_messages:
        assert any(expected in message for message in messages)


@pytest.mark.asyncio
async def test_collector_rejects_unresolved_url_template_before_network(monkeypatch):
    from app.models.watch_source import WatchSourceRepository
    from app.services.collector import _collector_fetch_handler

    monkeypatch.setattr(
        WatchSourceRepository,
        "get_by_id",
        lambda source_id: {
            "id": source_id,
            "is_enabled": 1,
            "url_template": "https://example.com/{unknown}",
            "request_headers": "{}",
        },
    )
    network_called = False

    def fail_if_called(*args, **kwargs):
        nonlocal network_called
        network_called = True
        raise AssertionError("network must not be called")

    monkeypatch.setattr("app.utils.safe_http.safe_http_request", fail_if_called)
    result = await _collector_fetch_handler(1, keyword="test", page=0)

    assert result["success"] is False
    assert "未解析" in result["error"]
    assert network_called is False


def test_docx_audit_deliverables_are_valid():
    for name in ("audit_report_v1.docx", "audit_report_v2.docx"):
        path = os.path.join(ROOT, "docs", name)
        assert zipfile.is_zipfile(path)
        with zipfile.ZipFile(path) as archive:
            assert "word/document.xml" in archive.namelist()
            assert "word/header1.xml" in archive.namelist()
            assert "word/footer1.xml" in archive.namelist()
            document = archive.read("word/document.xml").decode("utf-8")
            assert "FinderOS Security Audit Report" in document
            assert "TOC" in document


def test_configured_database_backup_is_functional(tmp_path, monkeypatch):
    source = tmp_path / "source.db"
    with sqlite3.connect(source) as conn:
        conn.execute("CREATE TABLE sample (value TEXT)")
        conn.execute("INSERT INTO sample VALUES ('ok')")
    monkeypatch.setattr("app.services.system_operations.settings.DB_PATH", str(source))
    monkeypatch.setattr("app.services.system_operations.settings.DB_BACKUP_PATH", str(tmp_path / "backups"))
    monkeypatch.setattr("app.services.system_operations.settings.DB_BACKUP_INTERVAL_DAYS", 1)
    monkeypatch.setattr("app.services.system_operations.settings.DB_BACKUP_KEEP_COUNT", 2)
    target = backup_database_if_due(now=1_800_000_000)
    assert target and os.path.exists(target)
    with sqlite3.connect(target) as conn:
        assert conn.execute("SELECT value FROM sample").fetchone()[0] == "ok"


def test_sentiment_periodic_work_is_offloaded_and_notifies():
    source = read("app/services/scheduler.py")
    assert 'ThreadPoolExecutor(max_workers=1, thread_name_prefix="sentiment")' in source
    assert "self._scan_future and not self._scan_future.done()" in source
    assert "send_alert_notification(result[\"total\"])" in source
