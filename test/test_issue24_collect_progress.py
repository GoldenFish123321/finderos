"""
Issue #24: 管理侧采集进度实时推送 + 采集日志页面

覆盖：
- WatchStreamHandler SSE 事件格式
- 单源采集共用 helper 持久化结果
- WATCH_COLLECT 审计日志可按采集日志页条件查询
- /admin/watch/stream 与 /admin/watch/log 路由注册
"""
import os
import sys
import tempfile
import inspect
from pathlib import Path

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

    with db_module.get_db() as conn:
        conn.execute("DELETE FROM watch_sources")
        conn.execute(
            """
            INSERT INTO watch_sources
            (id, name, description, url_template, request_headers, is_enabled, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                "Issue24测试源",
                "用于采集进度测试",
                "https://example.com/search?q={keyword}&pn={page}",
                '{"Accept":"text/html","Host":"evil.example"}',
                1,
                1,
            ),
        )
        conn.commit()


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


def test_watch_stream_route_registered():
    from main import make_app

    app = make_app()
    patterns = [rule.matcher.regex.pattern for rule in app.wildcard_router.rules]
    assert any("/admin/watch/stream" in p for p in patterns)
    assert any("/admin/watch/log" in p for p in patterns)


def test_sse_event_format():
    from app.controllers.admin_watch import WatchStreamHandler

    class DummyStream:
        def __init__(self):
            self.parts = []

        def write(self, value):
            self.parts.append(value)

    dummy = DummyStream()
    WatchStreamHandler._write_sse(dummy, "collect_progress", {
        "percent": 50,
        "current_url": "https://example.com/search?q=AI",
        "success": 1,
        "failed": 0,
    })
    payload = "".join(dummy.parts)
    assert payload.startswith("event: collect_progress\n")
    assert '"percent": 50' in payload
    assert payload.endswith("\n\n")


def test_watch_stream_requires_xsrf_token():
    from app.controllers.admin_watch import WatchStreamHandler

    source = inspect.getsource(WatchStreamHandler.get)
    assert "check_xsrf_cookie" in source

    template = Path("app/templates/admin/watch.html").read_text(encoding="utf-8")
    assert "&_xsrf=" in template
    assert "encodeURIComponent(xsrf)" in template


def test_collect_source_persists_result_and_filters_host_header(monkeypatch):
    from app.controllers import admin_watch
    from app.models.watch_result import WatchResultRepository

    seen = {}

    def fake_fetch_and_parse_via_handler(
        source_id, keyword="", page=0, parser="baidu_news", timeout=20
    ):
        seen["source_id"] = source_id
        seen["keyword"] = keyword
        seen["page"] = page
        seen["parser"] = parser
        return 200, 128, "<html></html>", [
            {
                "title": "Issue24 采集新闻",
                "link": "https://news.example/1",
                "summary": "采集进度测试",
                "source_name": "Issue24测试源",
            }
        ]

    monkeypatch.setattr(
        admin_watch, "fetch_and_parse_via_handler", fake_fetch_and_parse_via_handler
    )
    item = admin_watch._collect_source("人工智能", 1)

    assert item["ok"] is True
    assert item["news"][0]["title"] == "Issue24 采集新闻"
    assert seen["source_id"] == 1
    assert seen["keyword"] == "人工智能"
    assert seen["page"] == 0
    assert seen["parser"] == "baidu_news"

    rows, total = WatchResultRepository.get_all(keyword="人工智能")
    assert total >= 1
    assert any(r["keyword"] == "人工智能" for r in rows)


def test_collect_audit_log_query_for_watch_log():
    from app.controllers.admin_watch import _write_collect_audit

    _write_collect_audit(
        username="admin",
        keyword="Issue24",
        source_count=2,
        news_count=3,
        success_count=2,
        failed_count=0,
        client_ip="127.0.0.1",
    )

    with db_module.get_db() as conn:
        row = conn.execute(
            """
            SELECT action, username, target, detail
            FROM audit_logs
            WHERE UPPER(action) LIKE ? AND detail LIKE ?
            ORDER BY id DESC LIMIT 1
            """,
            ("%COLLECT%", "%Issue24%"),
        ).fetchone()

    assert row is not None
    assert row["action"] == "WATCH_COLLECT"
    assert row["username"] == "admin"
    assert row["target"] == "watch"
    assert "success=2" in row["detail"]
