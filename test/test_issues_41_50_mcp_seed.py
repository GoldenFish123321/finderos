"""Regression coverage for GitHub issues #41-#50."""
import json
import os
import tempfile
import unittest

from app.config.settings import settings
import app.models.db as db_module
from app.mcp.registry import discover_builtin_tool_definitions
from app.mcp.catalog import canonical_tool_names, upsert_builtin_tools
from migrate_db import _check_crawl4ai_permissions_migrated, _migrate_crawl4ai_permissions


class MCPSeedConsistencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.TemporaryDirectory()
        cls.db_path = os.path.join(cls.tmpdir.name, "fresh.db")
        cls.old_setting = settings.DB_PATH
        cls.old_module = db_module.DB_PATH
        settings.DB_PATH = cls.db_path
        db_module.DB_PATH = cls.db_path
        db_module.init_db()
        db_module.seed_default_data()

    @classmethod
    def tearDownClass(cls):
        settings.DB_PATH = cls.old_setting
        db_module.DB_PATH = cls.old_module
        cls.tmpdir.cleanup()

    def test_all_default_llm_employees_have_name_resolved_tool_permissions(self):
        with db_module.get_db() as conn:
            tools = {row["id"]: row["name"] for row in conn.execute(
                "SELECT id, name FROM mcp_tools"
            ).fetchall()}
            employees = conn.execute(
                "SELECT name, employee_type, mcp_tool_ids, mcp_tool_id FROM digital_employees"
            ).fetchall()
        for employee in employees:
            if employee["employee_type"] != "llm":
                continue
            assigned = json.loads(employee["mcp_tool_ids"] or "[]")
            self.assertTrue(assigned, employee["name"])
            self.assertTrue(all(tool_id in tools for tool_id in assigned), employee["name"])
        music = next(e for e in employees if e["name"] == "随机音乐")
        # API 型员工通过 mcp_tool_id（单工具绑定）而非 mcp_tool_ids（数组）
        self.assertEqual(music["employee_type"], "api", "随机音乐应为 API 型员工")
        music_tool_id = music["mcp_tool_id"]
        self.assertIsNotNone(music_tool_id, "随机音乐应通过 mcp_tool_id 绑定工具")
        self.assertEqual(tools[music_tool_id], "get_random_music")

    def test_fresh_install_seeds_full_skill_catalog_and_links_tools(self):
        with db_module.get_db() as conn:
            skills = conn.execute(
                "SELECT s.name, t.name AS tool_name FROM skills s "
                "LEFT JOIN mcp_tools t ON t.id = s.mcp_tool_id"
            ).fetchall()
        by_name = {row["name"]: row["tool_name"] for row in skills}
        self.assertGreaterEqual(len(by_name), 13)
        self.assertEqual(by_name["数据搜索"], "search_warehouse")
        self.assertEqual(by_name["深度采集"], "deep_collect_url")
        self.assertEqual(by_name["随机音乐"], "get_random_music")

    def test_fresh_tool_descriptions_use_canonical_catalog(self):
        with db_module.get_db() as conn:
            row = conn.execute(
                "SELECT description FROM mcp_tools WHERE name = ?",
                ("collect_with_crawl4ai",),
            ).fetchone()
        definition = next(
            item for item in discover_builtin_tool_definitions()
            if item["name"] == "collect_with_crawl4ai"
        )
        self.assertEqual(row["description"], definition["description"])

    def test_legacy_crawl4ai_flag_migrates_to_named_tool_ids(self):
        with db_module.get_db() as conn:
            conn.execute(
                "UPDATE digital_employees SET crawl4ai_enabled = 1, mcp_tool_ids = '[]' "
                "WHERE name = '采集专员'"
            )
            self.assertFalse(_check_crawl4ai_permissions_migrated(conn))
            _migrate_crawl4ai_permissions(conn)
            self.assertTrue(_check_crawl4ai_permissions_migrated(conn))
            row = conn.execute(
                "SELECT mcp_tool_ids FROM digital_employees WHERE name = '采集专员'"
            ).fetchone()
            names = [r["name"] for r in conn.execute(
                "SELECT name FROM mcp_tools WHERE id IN ({})".format(
                    ",".join("?" for _ in json.loads(row["mcp_tool_ids"]))
                ),
                json.loads(row["mcp_tool_ids"]),
            ).fetchall()]
        self.assertIn("collect_with_crawl4ai", names)
        self.assertIn("batch_deep_collect", names)

        with db_module.get_db() as conn:
            conn.execute(
                "UPDATE mcp_tools SET is_enabled = 0 WHERE name IN (?, ?)",
                ("collect_with_crawl4ai", "batch_deep_collect"),
            )
            conn.execute(
                "UPDATE digital_employees SET mcp_tool_ids = '[]' WHERE name = '采集专员'"
            )
            _migrate_crawl4ai_permissions(conn)
            self.assertTrue(_check_crawl4ai_permissions_migrated(conn))
            before = conn.execute(
                "SELECT mcp_tool_ids FROM digital_employees WHERE name = '采集专员'"
            ).fetchone()["mcp_tool_ids"]
            _migrate_crawl4ai_permissions(conn)
            after = conn.execute(
                "SELECT mcp_tool_ids FROM digital_employees WHERE name = '采集专员'"
            ).fetchone()["mcp_tool_ids"]
        self.assertEqual(before, after)

    def test_fallback_auto_discovers_all_builtin_handlers(self):
        definitions = discover_builtin_tool_definitions()
        names = {item["name"] for item in definitions}
        self.assertEqual(len(names), 20)
        self.assertIn("search_warehouse_fulltext", names)
        self.assertIn("get_system_stats", names)
        self.assertIn("invoke_digital_employee", names)
        self.assertIn("generate_image", names)
        self.assertIn("generate_video", names)
        search = next(item for item in definitions if item["name"] == "search_warehouse")
        self.assertEqual(search["input_schema"]["properties"]["limit"]["type"], "integer")
        collect = next(item for item in definitions if item["name"] == "batch_deep_collect")
        self.assertEqual(collect["input_schema"]["properties"]["urls"]["type"], "array")
        self.assertEqual(collect["input_schema"]["properties"]["urls"]["items"]["type"], "string")

    def test_partial_catalog_is_repaired_by_name(self):
        with db_module.get_db() as conn:
            conn.execute("DELETE FROM mcp_tools WHERE name = ?", ("get_system_stats",))
            conn.execute(
                "INSERT OR IGNORE INTO mcp_tools(name, display_name) VALUES (?, ?)",
                ("unrelated_custom_tool", "custom"),
            )
            upsert_builtin_tools(conn)
            names = {row["name"] for row in conn.execute("SELECT name FROM mcp_tools").fetchall()}
        self.assertTrue(canonical_tool_names().issubset(names))
        self.assertIn("unrelated_custom_tool", names)

    def test_startup_preserves_explicitly_cleared_permissions(self):
        with db_module.get_db() as conn:
            conn.execute("UPDATE skills SET mcp_tool_id = NULL WHERE name = '数据搜索'")
            conn.execute("UPDATE digital_employees SET mcp_tool_ids = '[]' WHERE name = '产业专员'")
        db_module.seed_default_data()
        with db_module.get_db() as conn:
            skill = conn.execute("SELECT mcp_tool_id FROM skills WHERE name = '数据搜索'").fetchone()
            employee = conn.execute(
                "SELECT mcp_tool_ids FROM digital_employees WHERE name = '产业专员'"
            ).fetchone()
        self.assertIsNone(skill["mcp_tool_id"])
        self.assertEqual(employee["mcp_tool_ids"], "[]")


if __name__ == "__main__":
    unittest.main()
