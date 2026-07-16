"""
test_skill.py — 技能管理模块测试

覆盖:
  - 技能 CRUD (创建/读取/更新/删除)
  - 技能启用/禁用
  - resolve_by_ids / resolve_by_names
  - get_skill_summaries (轻量摘要)
  - load_skill MCP 工具
  - 分页查询
"""
import json
import os
import sqlite3
import sys
import tempfile
import unittest

_skip_dead_code = unittest.skip("已移除: builtin 工具自动发现系统（discover_builtin_tool_definitions）")

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
_ORIGINAL_DB_PATH = db_module.DB_PATH
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
        mcp_tool_id     INTEGER DEFAULT NULL,
        is_enabled      INTEGER DEFAULT 1,
        created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.commit()
    conn.close()


def _seed_test_data():
    """插入测试技能数据。"""
    from app.models.skill import SkillRepository
    SkillRepository.create("测试技能1", "描述1", "这是prompt模板1")
    SkillRepository.create("测试技能2", "描述2", "使用 search_warehouse 工具搜索数据")
    SkillRepository.create("测试技能3", "描述3", "这是prompt模板3")


class TestSkillRepository(unittest.TestCase):
    """SkillRepository CRUD 测试。"""

    @classmethod
    def setUpClass(cls):
        db_module.DB_PATH = TEST_DB_PATH
        _setup_test_db()
        _seed_test_data()

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)
        db_module.DB_PATH = _ORIGINAL_DB_PATH

    # ── 查询测试 ──

    def test_get_all(self):
        from app.models.skill import SkillRepository
        rows, total = SkillRepository.get_all(page=1, page_size=10)
        self.assertEqual(total, 3)
        self.assertEqual(len(rows), 3)

    def test_get_by_id(self):
        from app.models.skill import SkillRepository
        skill = SkillRepository.get_by_id(1)
        self.assertIsNotNone(skill)
        self.assertEqual(skill["name"], "测试技能1")

    def test_get_by_name(self):
        from app.models.skill import SkillRepository
        skill = SkillRepository.get_by_name("测试技能2")
        self.assertIsNotNone(skill)
        self.assertEqual(skill["name"], "测试技能2")

    def test_get_enabled(self):
        from app.models.skill import SkillRepository
        skills = SkillRepository.get_enabled()
        self.assertEqual(len(skills), 3)

    # ── 写入测试 ──

    def test_create_duplicate_name(self):
        from app.models.skill import SkillRepository
        new_id = SkillRepository.create("测试技能1", "重复", "模板")
        self.assertEqual(new_id, -1)  # 唯一约束

    def test_create_and_verify(self):
        from app.models.skill import SkillRepository
        new_id = SkillRepository.create("新技能", "新描述", "新模板内容")
        self.assertGreater(new_id, 0)
        skill = SkillRepository.get_by_id(new_id)
        self.assertEqual(skill["name"], "新技能")
        self.assertEqual(skill["prompt_template"], "新模板内容")
        # 清理
        SkillRepository.delete(new_id)

    def test_update(self):
        from app.models.skill import SkillRepository
        skill = SkillRepository.get_by_id(3)
        ok = SkillRepository.update(skill["id"], "更新技能", "更新描述", "更新后的模板")
        self.assertTrue(ok)
        updated = SkillRepository.get_by_id(3)
        self.assertEqual(updated["name"], "更新技能")
        self.assertEqual(updated["prompt_template"], "更新后的模板")
        # 还原
        SkillRepository.update(skill["id"], "测试技能3", "描述3", "这是prompt模板3")

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
        self.assertEqual(stats["enabled"], 3)


class TestLoadSkillMCPTool(unittest.TestCase):
    """MCP load_skill 工具测试。"""

    @classmethod
    def setUpClass(cls):
        db_module.DB_PATH = TEST_DB_PATH
        _setup_test_db()
        _seed_test_data()

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)
        db_module.DB_PATH = _ORIGINAL_DB_PATH

    def test_load_skill_returns_prompt_template(self):
        """加载技能，返回 prompt 模板内容。"""
        from app.mcp.builtin_tools.system_tools import _load_skill
        result = _load_skill("测试技能1")
        self.assertTrue(result["success"])
        self.assertEqual(result["skill_name"], "测试技能1")
        self.assertIn("这是prompt模板1", result["content"])
        self.assertIn("usage", result)

    def test_load_skill_not_found(self):
        """加载不存在的技能。"""
        from app.mcp.builtin_tools.system_tools import _load_skill
        result = _load_skill("不存在的技能")
        self.assertFalse(result["success"])
        self.assertIn("不存在", result["error"])

    def test_load_skill_disabled(self):
        """加载已禁用的技能。"""
        from app.models.skill import SkillRepository
        from app.mcp.builtin_tools.system_tools import _load_skill
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

    @_skip_dead_code
    def test_load_skill_schema(self):
        """验证 load_skill 的 JSON Schema 包含 skill_name 参数。"""
        from app.mcp.registry import discover_builtin_tool_definitions
        definitions = discover_builtin_tool_definitions()
        load_skill_def = None
        for t in definitions:
            if t["name"] == "load_skill":
                load_skill_def = t
                break
        self.assertIsNotNone(load_skill_def)
        self.assertEqual(load_skill_def["input_schema"]["required"], ["skill_name"])


@_skip_dead_code
class TestAllToolDefinitions(unittest.TestCase):
    """验证 discover_builtin_tool_definitions() 自动发现所有 builtin 工具（替代旧 ALL_TOOL_DEFINITIONS）。"""

    # 截至 v1.3.0-beta，builtin_tools/ 包中共有 20 个工具
    MIN_EXPECTED_TOOLS = {
        # 数据仓库类
        "search_warehouse", "get_recent_warehouse_data", "get_warehouse_stats",
        "search_warehouse_fulltext",
        # 数据采集类
        "deep_collect_url", "collect_web_data", "list_watch_sources",
        # 数字员工类
        "list_digital_employees", "invoke_digital_employee",
        # AI 模型类
        "list_ai_models", "get_default_model",
        # Crawl4ai 增强类
        "collect_with_crawl4ai", "batch_deep_collect",
        # 音乐/娱乐类
        "get_random_music",
        # 对话管理类
        "list_conversations", "get_conversation_messages",
        # 技能管理类
        "load_skill",
        # 系统管理类
        "get_system_stats",
        # v1.3.0 新增：多模态媒体生成
        "generate_image", "generate_video",
    }

    def test_all_expected_tools_discovered(self):
        """discover_builtin_tool_definitions() 应包含全部预期的内置工具。"""
        from app.mcp.registry import discover_builtin_tool_definitions
        definitions = discover_builtin_tool_definitions()
        actual = {t["name"] for t in definitions}
        missing = self.MIN_EXPECTED_TOOLS - actual
        self.assertEqual(missing, set(), f"缺失工具: {missing}")

    def test_all_tools_have_handler(self):
        """每个工具定义必须有 handler 且 handler 可调用。"""
        from app.mcp.registry import discover_builtin_tool_definitions
        for t in discover_builtin_tool_definitions():
            self.assertIn("handler", t, f"工具 {t['name']} 缺少 handler")
            self.assertTrue(callable(t["handler"]), f"工具 {t['name']} 的 handler 不可调用")

    def test_all_tools_have_required_schema(self):
        """每个工具定义必须有 name、description、input_schema。"""
        from app.mcp.registry import discover_builtin_tool_definitions
        for t in discover_builtin_tool_definitions():
            self.assertIn("name", t)
            self.assertIn("description", t)
            self.assertIn("input_schema", t)
            self.assertIn("type", t["input_schema"])
            self.assertEqual(t["input_schema"]["type"], "object")


class TestPromptFileLoading(unittest.TestCase):
    """测试 prompt 从 docs/prompts/ 文件加载的正确性。

    v1.9.8 将 24 个硬编码 AI prompt 提取到 docs/prompts/ 独立文件中，
    确保文件可读且内容不退化。
    """

    def setUp(self):
        project_root = os.path.dirname(os.path.dirname(__file__))
        self.prompts_dir = os.path.join(project_root, "docs", "prompts")

    def _read_prompt_file(self, path: str) -> str:
        with open(os.path.join(self.prompts_dir, path), "r", encoding="utf-8") as f:
            return f.read()

    def test_system_prompts_exist_and_nonempty(self):
        """4 个 system prompt 文件存在且内容非空。"""
        files = ["system_identity.txt", "chart_instruction.txt",
                 "tool_usage_instruction.txt", "media_instruction.txt"]
        for f in files:
            content = self._read_prompt_file(f)
            self.assertGreater(len(content), 50, f"{f} 内容过短 ({len(content)} chars)")

    def test_system_prompts_have_expected_keywords(self):
        """system prompt 文件包含预期关键词。"""
        identity = self._read_prompt_file("system_identity.txt")
        self.assertIn("DataFinderAgentOS", identity)
        chart = self._read_prompt_file("chart_instruction.txt")
        self.assertIn("ECharts", chart)
        tools = self._read_prompt_file("tool_usage_instruction.txt")
        self.assertIn("search_warehouse", tools)
        media = self._read_prompt_file("media_instruction.txt")
        self.assertIn("generate_image", media)

    def test_employee_prompts_exist_and_nonempty(self):
        """6 个员工 prompt 文件存在且内容非空。"""
        employees = ["industry_analyst", "tianji_assistant", "collector",
                     "copywriter", "news_aggregator", "science_pop"]
        for emp in employees:
            content = self._read_prompt_file(f"employees/{emp}.txt")
            self.assertGreater(len(content), 50,
                               f"employees/{emp}.txt 内容过短 ({len(content)} chars)")

    def test_skill_prompts_exist_and_nonempty(self):
        """14 个技能 prompt 文件存在且内容非空。"""
        skills = ["data_stats", "data_search", "news_summary", "deep_collect",
                  "translation", "industry_analysis", "policy_interpretation",
                  "competitive_analysis", "trend_prediction", "copywriting",
                  "code_assist", "encyclopedia", "info_retrieval", "data_analysis"]
        for skill in skills:
            content = self._read_prompt_file(f"skills/{skill}.txt")
            self.assertGreater(len(content), 50,
                               f"skills/{skill}.txt 内容过短 ({len(content)} chars)")

    def test_db_load_prompt_file_returns_match(self):
        """db.py 的 _load_prompt_file() 返回值与直接读文件一致。"""
        from app.models.db import _load_prompt_file
        for path in ["employees/collector.txt", "skills/data_stats.txt"]:
            direct = self._read_prompt_file(path)
            via_func = _load_prompt_file(path)
            self.assertEqual(direct, via_func,
                             f"_load_prompt_file('{path}') 与直接读文件不一致")

    def test_total_prompt_count(self):
        """验证 prompt 文件总数（24 = 4 system + 6 employee + 14 skill）。"""
        count = 0
        for root, dirs, files in os.walk(self.prompts_dir):
            count += sum(1 for f in files if f.endswith(".txt"))
        self.assertEqual(count, 24,
                         f"预期 24 个 prompt 文件，实际 {count} 个")


if __name__ == "__main__":
    unittest.main(verbosity=2)
