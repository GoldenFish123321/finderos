"""
test_skill.py — 技能管理模块测试

覆盖:
  - 技能 CRUD (创建/读取/更新/删除)
  - 技能启用/禁用
  - resolve_by_ids / resolve_by_names
  - get_skill_summaries (轻量摘要)
  - load_skill MCP 工具
  - 分页查询 + 类型筛选
"""
import json
import os
import sqlite3
import sys
import tempfile
import unittest

# 将项目根目录加入路径
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# 使用临时数据库（避免污染生产数据库）
_temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
TEST_DB_PATH = _temp_db.name
_temp_db.close()

# 覆盖数据库路径
import app.config.settings as settings
settings.DB_PATH = TEST_DB_PATH

# 覆盖 app.models.db 中的 DB_PATH
import app.models.db as db_module
db_module.DB_PATH = TEST_DB_PATH


def _setup_test_db():
    """创建测试数据库（仅 skills 表，不触发全量种子数据）。"""
    os.makedirs(os.path.dirname(TEST_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(TEST_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS skills (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        name            TEXT UNIQUE NOT NULL,
        description     TEXT DEFAULT '',
        skill_type      TEXT NOT NULL DEFAULT 'prompt',
        prompt_template TEXT DEFAULT '',
        function_name   TEXT DEFAULT '',
        function_params TEXT DEFAULT '{}',
        is_enabled      INTEGER DEFAULT 1,
        created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.commit()
    conn.close()


def _seed_test_data():
    """插入测试技能数据。"""
    from app.models.skill import SkillRepository
    SkillRepository.create("测试技能1", "描述1", "prompt", "这是prompt模板1", "", "{}")
    SkillRepository.create("测试技能2", "描述2", "function", "", "search_warehouse", '{"keyword":"test"}')
    SkillRepository.create("测试技能3", "描述3", "prompt", "这是prompt模板3", "", "{}")


class TestSkillRepository(unittest.TestCase):
    """SkillRepository CRUD 测试。"""

    @classmethod
    def setUpClass(cls):
        _setup_test_db()
        _seed_test_data()

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)

    # ── 查询测试 ──

    def test_get_all(self):
        from app.models.skill import SkillRepository
        rows, total = SkillRepository.get_all(page=1, page_size=10)
        self.assertEqual(total, 3)
        self.assertEqual(len(rows), 3)

    def test_get_all_filter_by_type(self):
        from app.models.skill import SkillRepository
        rows, total = SkillRepository.get_all(page=1, page_size=10, skill_type="prompt")
        self.assertEqual(total, 2)
        self.assertTrue(all(r["skill_type"] == "prompt" for r in rows))

    def test_get_by_id(self):
        from app.models.skill import SkillRepository
        skill = SkillRepository.get_by_id(1)
        self.assertIsNotNone(skill)
        self.assertEqual(skill["name"], "测试技能1")

    def test_get_by_name(self):
        from app.models.skill import SkillRepository
        skill = SkillRepository.get_by_name("测试技能2")
        self.assertIsNotNone(skill)
        self.assertEqual(skill["skill_type"], "function")

    def test_get_enabled(self):
        from app.models.skill import SkillRepository
        skills = SkillRepository.get_enabled()
        self.assertEqual(len(skills), 3)

    # ── 写入测试 ──

    def test_create_duplicate_name(self):
        from app.models.skill import SkillRepository
        new_id = SkillRepository.create("测试技能1", "重复", "prompt", "模板", "", "{}")
        self.assertEqual(new_id, -1)  # 唯一约束

    def test_create_and_verify(self):
        from app.models.skill import SkillRepository
        new_id = SkillRepository.create("新技能", "新描述", "prompt", "新模板", "", "{}")
        self.assertGreater(new_id, 0)
        skill = SkillRepository.get_by_id(new_id)
        self.assertEqual(skill["name"], "新技能")
        # 清理
        SkillRepository.delete(new_id)

    def test_update(self):
        from app.models.skill import SkillRepository
        skill = SkillRepository.get_by_id(3)
        ok = SkillRepository.update(skill["id"], "更新技能", "更新描述",
                                     "function", "", "deep_collect_url", '{"url":"test"}')
        self.assertTrue(ok)
        updated = SkillRepository.get_by_id(3)
        self.assertEqual(updated["name"], "更新技能")
        self.assertEqual(updated["function_name"], "deep_collect_url")
        # 还原
        SkillRepository.update(skill["id"], "测试技能3", "描述3",
                               "prompt", "这是prompt模板3", "", "{}")

    def test_toggle_enabled(self):
        from app.models.skill import SkillRepository
        status = SkillRepository.toggle_enabled(1)
        self.assertIn(status, [0, 1])
        # 还原
        SkillRepository.toggle_enabled(1)

    def test_toggle_nonexistent(self):
        from app.models.skill import SkillRepository
        status = SkillRepository.toggle_enabled(999)
        self.assertEqual(status, -1)

    # ── 批量查询测试 ──

    def test_resolve_by_ids(self):
        from app.models.skill import SkillRepository
        skills = SkillRepository.resolve_by_ids([1, 2])
        self.assertEqual(len(skills), 2)
        names = {s["name"] for s in skills}
        self.assertIn("测试技能1", names)
        self.assertIn("测试技能2", names)

    def test_resolve_by_ids_empty(self):
        from app.models.skill import SkillRepository
        skills = SkillRepository.resolve_by_ids([])
        self.assertEqual(len(skills), 0)

    def test_resolve_by_names(self):
        from app.models.skill import SkillRepository
        skills = SkillRepository.resolve_by_names(["测试技能1"])
        self.assertEqual(len(skills), 1)
        self.assertEqual(skills[0]["id"], 1)

    def test_get_skill_summaries(self):
        from app.models.skill import SkillRepository
        summaries = SkillRepository.get_skill_summaries(skill_ids=[1, 2, 3])
        self.assertEqual(len(summaries), 3)
        self.assertIn("name", summaries[0])
        self.assertIn("description", summaries[0])
        # 不应包含 prompt_template 等大字段
        self.assertNotIn("prompt_template", summaries[0])

    # ── 统计测试 ──

    def test_get_stats(self):
        from app.models.skill import SkillRepository
        stats = SkillRepository.get_stats()
        self.assertEqual(stats["total"], 3)
        self.assertEqual(stats["prompt_count"], 2)
        self.assertEqual(stats["function_count"], 1)


class TestLoadSkillMCPTool(unittest.TestCase):
    """MCP load_skill 工具测试。"""

    @classmethod
    def setUpClass(cls):
        _setup_test_db()
        _seed_test_data()

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)

    def test_load_skill_prompt_type(self):
        """加载 prompt 型技能，返回完整模板。"""
        from app.mcp.tools import _load_skill
        result = _load_skill("测试技能1")
        self.assertTrue(result["success"])
        self.assertEqual(result["skill_type"], "prompt")
        self.assertIn("这是prompt模板1", result["content"])
        self.assertIn("usage", result)

    def test_load_skill_function_type(self):
        """加载 function 型技能，返回工具映射。"""
        from app.mcp.tools import _load_skill
        result = _load_skill("测试技能2")
        self.assertTrue(result["success"])
        self.assertEqual(result["skill_type"], "function")
        self.assertEqual(result["function_name"], "search_warehouse")
        self.assertIsInstance(result["function_params"], dict)

    def test_load_skill_not_found(self):
        """加载不存在的技能。"""
        from app.mcp.tools import _load_skill
        result = _load_skill("不存在的技能")
        self.assertFalse(result["success"])
        self.assertIn("不存在", result["error"])

    def test_load_skill_disabled(self):
        """加载已禁用的技能。"""
        from app.models.skill import SkillRepository
        from app.mcp.tools import _load_skill
        # 禁用技能1
        SkillRepository.toggle_enabled(1)
        result = _load_skill("测试技能1")
        self.assertFalse(result["success"])
        self.assertIn("已被禁用", result["error"])
        # 还原
        SkillRepository.toggle_enabled(1)


class TestSkillMCPRegistration(unittest.TestCase):
    """验证 load_skill 工具是否注册到 MCP Server。"""

    def test_tool_registered(self):
        from app.mcp.tools import register_all_tools, get_tool_names
        from app.mcp.server import MCPServer
        # 创建独立的 server 实例避免单例污染
        server = MCPServer()
        register_all_tools(server)
        names = get_tool_names()
        self.assertIn("load_skill", names)

    def test_load_skill_schema(self):
        """验证 load_skill 的 JSON Schema 包含 skill_name 参数。"""
        from app.mcp.tools import ALL_TOOL_DEFINITIONS
        load_skill_def = None
        for t in ALL_TOOL_DEFINITIONS:
            if t["name"] == "load_skill":
                load_skill_def = t
                break
        self.assertIsNotNone(load_skill_def)
        self.assertEqual(load_skill_def["input_schema"]["required"], ["skill_name"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
