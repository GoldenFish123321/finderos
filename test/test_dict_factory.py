"""
test_dict_factory.py — 验证 db.py dict_factory 修复 (v0.4.2)

验证：
1. 数据库查询返回 dict 而非 sqlite3.Row
2. dict 支持 .get() 方法（修复前 sqlite3.Row 不支持导致 AttributeError）
3. 所有 MCP 工具处理函数中 .get() 调用正常工作
4. WatchSourceRepository 返回的 dict 支持 .get()
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.db import get_connection, get_db, _dict_factory


def test_dict_factory_returns_dict():
    """测试 dict_factory 返回 dict 类型。"""
    conn = get_connection()
    try:
        row = conn.execute("SELECT 1 AS test, 'hello' AS greeting").fetchone()
        assert isinstance(row, dict), f"期望 dict，实际 {type(row)}"
        assert row["test"] == 1
        assert row["greeting"] == "hello"
    finally:
        conn.close()


def test_dict_supports_get_method():
    """测试 dict 支持 .get() 方法（sqlite3.Row 不支持）。"""
    conn = get_connection()
    try:
        row = conn.execute("SELECT 1 AS id, 'test' AS name").fetchone()
        # .get() 是 dict 的核心功能，sqlite3.Row 不支持
        assert row.get("id") == 1
        assert row.get("name") == "test"
        assert row.get("nonexistent") is None
        assert row.get("nonexistent", "default") == "default"
    finally:
        conn.close()


def test_watch_source_get_method():
    """测试 WatchSourceRepository 返回的 dict 支持 .get()。"""
    from app.models.watch_source import WatchSourceRepository

    sources = WatchSourceRepository.get_enabled()
    for s in sources:
        # 修复前: 'sqlite3.Row' object has no attribute 'get'
        # 修复后: dict 支持 .get()
        desc = s.get("description", "")
        url_tpl = s.get("url_template", "")
        assert isinstance(desc, str)
        assert isinstance(url_tpl, str)
        # 也验证方括号访问仍然正常
        assert isinstance(s["id"], int)
        assert isinstance(s["name"], str)


def test_list_watch_sources_tool():
    """测试 list_watch_sources MCP 工具（直接触发原始 bug）。"""
    from app.mcp.builtin_tools.collect_tools import _list_watch_sources

    result = _list_watch_sources()
    assert "total" in result
    assert "sources" in result
    assert isinstance(result["sources"], list)
    for s in result["sources"]:
        assert "id" in s
        assert "name" in s
        assert "description" in s
        assert "url_template" in s


def test_dict_supports_key_access():
    """测试 dict 支持方括号键访问（兼容原有代码风格）。"""
    conn = get_connection()
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS _test_dict (id INTEGER, name TEXT)")
        conn.execute("INSERT INTO _test_dict VALUES (1, 'alpha')")
        conn.commit()
        row = conn.execute("SELECT * FROM _test_dict WHERE id = 1").fetchone()
        assert row["id"] == 1
        assert row["name"] == "alpha"
    finally:
        conn.execute("DROP TABLE IF EXISTS _test_dict")
        conn.commit()
        conn.close()


def test_dict_supports_iteration():
    """测试 dict 支持迭代（兼容原有 for row in rows 模式）。"""
    conn = get_connection()
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS _test_iter (id INTEGER)")
        conn.execute("INSERT INTO _test_iter VALUES (1), (2), (3)")
        conn.commit()
        rows = conn.execute("SELECT * FROM _test_iter ORDER BY id").fetchall()
        assert len(rows) == 3
        ids = [r["id"] for r in rows]
        assert ids == [1, 2, 3]
    finally:
        conn.execute("DROP TABLE IF EXISTS _test_iter")
        conn.commit()
        conn.close()


def test_dict_factory_with_pragma():
    """测试 PRAGMA 查询也返回 dict（PRAGMA table_info 用于迁移检查）。"""
    conn = get_connection()
    try:
        rows = conn.execute("PRAGMA table_info(users)").fetchall()
        assert len(rows) > 0
        for row in rows:
            # 原来用 row[1] 访问列名，现在用 row["name"]
            assert "name" in row
            assert "type" in row
            assert isinstance(row["name"], str)
            assert isinstance(row.get("name"), str)
    finally:
        conn.close()


if __name__ == "__main__":
    test_dict_factory_returns_dict()
    print("✅ test_dict_factory_returns_dict 通过")
    test_dict_supports_get_method()
    print("✅ test_dict_supports_get_method 通过")
    test_watch_source_get_method()
    print("✅ test_watch_source_get_method 通过")
    test_list_watch_sources_tool()
    print("✅ test_list_watch_sources_tool 通过")
    test_dict_supports_key_access()
    print("✅ test_dict_supports_key_access 通过")
    test_dict_supports_iteration()
    print("✅ test_dict_supports_iteration 通过")
    test_dict_factory_with_pragma()
    print("✅ test_dict_factory_with_pragma 通过")
    print("\n🎉 所有测试通过！dict_factory 修复验证成功。")
