"""Three-source collection requirement: config, parsing, routing and persistence."""

import sqlite3
from pathlib import Path

import pytest

import app.models.db as db_module
from app.models.db import init_db, seed_default_data
from app.models.watch_source import (
    WATCH_SOURCE_PARSERS,
    WatchSourceRepository,
    resolve_source_parser,
)
from app.services.collector import parse_bing_rss


@pytest.fixture
def seeded_db(tmp_path, monkeypatch):
    db_path = tmp_path / "three-sources.db"
    monkeypatch.setattr(db_module, "DB_PATH", str(db_path))
    init_db()
    seed_default_data()
    return db_path


def test_fresh_database_has_three_enabled_sources_with_explicit_parsers(seeded_db):
    sources = WatchSourceRepository.get_enabled()
    by_name = {source["name"]: source for source in sources}

    assert {"百度新闻", "搜狗搜索", "Bing RSS"} <= set(by_name)
    assert by_name["百度新闻"]["parser"] == "baidu_news"
    assert by_name["搜狗搜索"]["parser"] == "sogou_news"
    assert by_name["Bing RSS"]["parser"] == "bing_rss"


def test_seed_repairs_existing_one_source_database_without_overwriting_it(seeded_db):
    with db_module.get_db() as conn:
        conn.execute("DELETE FROM watch_sources WHERE name != '百度新闻'")
        conn.execute(
            "UPDATE watch_sources SET description = ? WHERE name = '百度新闻'",
            ("用户自定义描述",),
        )

    seed_default_data()
    sources = WatchSourceRepository.get_enabled()
    by_name = {source["name"]: source for source in sources}
    assert len(by_name) >= 3
    assert by_name["百度新闻"]["description"] == "用户自定义描述"
    assert {"搜狗搜索", "Bing RSS"} <= set(by_name)


def test_old_watch_source_schema_is_migrated_and_completed(tmp_path, monkeypatch):
    db_path = tmp_path / "old-watch-source.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE watch_sources ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, "
        "description TEXT DEFAULT '', url_template TEXT NOT NULL, "
        "request_headers TEXT DEFAULT '{}', is_enabled INTEGER DEFAULT 1, "
        "sort_order INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    )
    conn.execute(
        "INSERT INTO watch_sources (name, url_template) VALUES (?, ?)",
        ("百度新闻", "https://www.baidu.com/s?word={keyword}&pn={page}"),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(db_module, "DB_PATH", str(db_path))
    init_db()
    seed_default_data()

    with db_module.get_db() as migrated:
        columns = {row["name"] for row in migrated.execute("PRAGMA table_info(watch_sources)")}
        rows = migrated.execute(
            "SELECT name, parser FROM watch_sources ORDER BY sort_order, id"
        ).fetchall()
    assert "parser" in columns
    assert "schedule_interval" in columns
    assert len(rows) >= 3
    assert next(row for row in rows if row["name"] == "百度新闻")["parser"] == "baidu_news"


def test_bing_rss_parser_uses_structured_xml():
    rss = """<?xml version="1.0" encoding="utf-8"?>
    <rss version="2.0"><channel><title>测试</title>
      <item><title>人工智能产业发展报告</title>
        <link>https://example.com/news/1</link>
        <description><![CDATA[<b>报告摘要</b>与趋势分析]]></description>
        <source>示例媒体</source></item>
    </channel></rss>"""
    rows = parse_bing_rss(rss)
    assert rows == [{
        "title": "人工智能产业发展报告",
        "link": "https://example.com/news/1",
        "summary": "报告摘要与趋势分析",
        "source_name": "示例媒体",
    }]


def test_bing_rss_parser_rejects_entities_and_malformed_xml():
    entity_rss = """<!DOCTYPE rss [
      <!ENTITY a "1234567890"><!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">
    ]><rss><channel><item><title>&b;&b;&b;&b;</title>
      <link>https://example.com/1</link></item></channel></rss>"""
    assert parse_bing_rss(entity_rss) == []
    assert parse_bing_rss("<rss><channel><item></rss>") == []


def test_bing_rss_parser_bounds_persisted_fields():
    rss = (
        "<rss><channel><item><title>" + "A" * 500 + "</title>"
        "<link>https://example.com/" + "x" * 3000 + "</link>"
        "<description>摘要</description><source>" + "S" * 200 + "</source>"
        "</item></channel></rss>"
    )
    row = parse_bing_rss(rss)[0]
    assert len(row["title"]) == 300
    assert len(row["link"]) == 2048
    assert len(row["source_name"]) == 100


def test_parser_resolution_prefers_configuration_and_has_safe_fallback():
    assert resolve_source_parser({"parser": "bing_rss", "url_template": "https://custom.test"}) == "bing_rss"
    assert resolve_source_parser({"url_template": "https://www.sogou.com/search"}) == "sogou_news"
    assert resolve_source_parser({"parser": "invalid", "url_template": "https://example.com"}) == "generic"
    assert set(WATCH_SOURCE_PARSERS) == {"baidu_news", "sogou_news", "bing_rss", "generic"}


def test_explicit_generic_parser_is_not_overwritten_on_restart(seeded_db):
    with db_module.get_db() as conn:
        conn.execute("UPDATE watch_sources SET parser = 'generic' WHERE name = 'Bing RSS'")
    init_db()
    source = next(
        row for row in WatchSourceRepository.get_enabled() if row["name"] == "Bing RSS"
    )
    assert source["parser"] == "generic"


def test_each_source_routes_to_its_parser_and_persists_results(seeded_db, monkeypatch):
    from app.controllers import admin_watch
    from app.models.watch_result import WatchResultRepository

    seen = {}

    def fake_fetch(source_id, keyword="", page=0, parser="generic", timeout=20):
        source = WatchSourceRepository.get_by_id(source_id)
        seen[source["name"]] = parser
        return 200, 128, "payload", [{
            "title": f"{source['name']} 人工智能新闻",
            "link": f"https://example.com/{source_id}",
            "summary": "三源采集持久化测试",
            "source_name": source["name"],
        }]

    monkeypatch.setattr(admin_watch, "fetch_and_parse_via_handler", fake_fetch)
    for source in WatchSourceRepository.get_enabled():
        if source["name"] in {"百度新闻", "搜狗搜索", "Bing RSS"}:
            result = admin_watch._collect_source("人工智能", source["id"])
            assert result["ok"] is True

    assert seen == {
        "百度新闻": "baidu_news",
        "搜狗搜索": "sogou_news",
        "Bing RSS": "bing_rss",
    }
    rows, total = WatchResultRepository.get_all(keyword="人工智能")
    assert total == 3
    assert {row["source_name"] for row in rows} == {"百度新闻", "搜狗搜索", "Bing RSS"}


def test_repository_rejects_unknown_parser(seeded_db):
    assert not WatchSourceRepository.create(
        "错误解析器", "", "https://example.com?q={keyword}", parser="unknown"
    )


def test_admin_form_exposes_parser_and_schedule_configuration():
    template = Path("app/templates/admin/watch_source_form.html").read_text(encoding="utf-8")
    assert 'name="parser"' in template
    assert 'name="schedule_interval"' in template
    assert "parser_options.items()" in template
