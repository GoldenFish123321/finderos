"""
test_bug32_employee_ui_display.py — 员工列表 UI 显示修复测试

覆盖:
  - Bug #32: 模型名称显示 "None"（应为 "默认模型"）
  - Bug #32: 技能标签显示为 dict 字符串（应为技能名称）
  - skills_list 类型验证：确保为字符串列表
  - model_name 为 None 时的默认值回退
"""
import json
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# 使用临时数据库
_temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
TEST_DB_PATH = _temp_db.name
_temp_db.close()

import app.config.settings as settings
settings.DB_PATH = TEST_DB_PATH

import app.models.db as db_module
db_module.DB_PATH = TEST_DB_PATH


def _setup_test_db():
    """创建测试数据库表结构。"""
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

    conn.execute("""CREATE TABLE IF NOT EXISTS ai_models (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        name            TEXT NOT NULL,
        provider        TEXT DEFAULT '',
        model_name      TEXT DEFAULT '',
        api_base        TEXT DEFAULT '',
        api_key         TEXT DEFAULT '',
        is_enabled      INTEGER DEFAULT 1,
        created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    conn.execute("""CREATE TABLE IF NOT EXISTS digital_employees (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        name            TEXT NOT NULL,
        employee_type   TEXT DEFAULT 'llm',
        description     TEXT DEFAULT '',
        model_id        INTEGER,
        system_prompt   TEXT DEFAULT '',
        skills          TEXT DEFAULT '[]',
        crawl4ai_enabled INTEGER DEFAULT 0,
        api_url         TEXT DEFAULT '',
        api_method      TEXT DEFAULT 'GET',
        api_headers     TEXT DEFAULT '{}',
        api_params_template TEXT DEFAULT '',
        response_render_template TEXT DEFAULT '',
        api_secret      TEXT DEFAULT '',
        is_enabled      INTEGER DEFAULT 1,
        created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    conn.commit()
    conn.close()


def _seed_test_data():
    """插入测试数据（使用原始 SQL 避免依赖完整的 Repository 方法）。"""
    conn = sqlite3.connect(TEST_DB_PATH)

    # 创建技能
    conn.execute(
        "INSERT INTO skills (name, description, skill_type, function_name, function_params) "
        "VALUES (?, ?, ?, ?, ?)",
        ("数据搜索", "在数据仓库中搜索", "function", "search_warehouse", '{"keyword":"test"}'),
    )
    conn.execute(
        "INSERT INTO skills (name, description, skill_type, function_name, function_params) "
        "VALUES (?, ?, ?, ?, ?)",
        ("深度采集", "深度抓取网页", "function", "deep_collect_url", '{"url":"test"}'),
    )

    # 创建模型（最小字段集）
    conn.execute(
        "INSERT INTO ai_models (name, provider, model_name, api_base, api_key) "
        "VALUES (?, ?, ?, ?, ?)",
        ("测试模型", "openai", "gpt-4-test", "https://api.test.com", "sk-test"),
    )

    # 创建 LLM 型员工（有 model_id）
    conn.execute(
        "INSERT INTO digital_employees (name, employee_type, description, "
        "model_id, skills, crawl4ai_enabled) VALUES (?, ?, ?, ?, ?, ?)",
        ("采集专员LLM", "llm", "专注于数据采集", 1, json.dumps([1, 2]), 1),
    )

    # 创建 LLM 型员工（无 model_id，model_name 应为 None）
    conn.execute(
        "INSERT INTO digital_employees (name, employee_type, description, "
        "model_id, skills, crawl4ai_enabled) VALUES (?, ?, ?, ?, ?, ?)",
        ("无模型员工", "llm", "没有关联模型", None, json.dumps([1]), 0),
    )

    conn.commit()
    conn.close()


class TestEmployeeUISkillsDisplay(unittest.TestCase):
    """测试技能列表在 UI 中的显示格式。"""

    @classmethod
    def setUpClass(cls):
        _setup_test_db()
        _seed_test_data()

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)

    def test_skills_list_are_strings_not_dicts(self):
        """Bug #32: 验证 skills_list 中的元素是字符串（技能名称），而非 dict。"""
        from app.models.digital_employee import DigitalEmployeeRepository
        from app.models.skill import SkillRepository

        rows, total = DigitalEmployeeRepository.get_all(page=1, page_size=10)
        self.assertGreaterEqual(len(rows), 1)

        for emp in rows:
            raw_skills = json.loads(emp.get("skills", "[]"))
            if raw_skills and isinstance(raw_skills[0], int):
                resolved = SkillRepository.resolve_by_ids(raw_skills)
                skills_list = [s["name"] for s in resolved] if resolved else []
            elif raw_skills and isinstance(raw_skills[0], str):
                resolved_names = SkillRepository.resolve_by_names(raw_skills)
                skills_list = [s["name"] for s in resolved_names] if resolved_names else raw_skills
            else:
                skills_list = []

            # 关键断言：每个元素必须是字符串
            for skill_item in skills_list:
                self.assertIsInstance(
                    skill_item, str,
                    f"skills_list 元素应为字符串，但得到 {type(skill_item)}: {skill_item}"
                )

    def test_llm_employee_skills_resolved_to_names(self):
        """验证 LLM 员工的技能 ID 被正确解析为技能名称。"""
        from app.models.digital_employee import DigitalEmployeeRepository
        from app.models.skill import SkillRepository

        emp = DigitalEmployeeRepository.get_by_id(1)
        self.assertIsNotNone(emp)
        self.assertEqual(emp["employee_type"], "llm")

        raw_skills = json.loads(emp.get("skills", "[]"))
        self.assertEqual(raw_skills, [1, 2])  # 原始存储为 ID 数组

        resolved = SkillRepository.resolve_by_ids(raw_skills)
        self.assertEqual(len(resolved), 2)

        skill_names = [s["name"] for s in resolved]
        self.assertIn("数据搜索", skill_names)
        self.assertIn("深度采集", skill_names)

    def test_model_name_none_fallback(self):
        """Bug #32: 验证 model_name 为 None 时的默认值回退逻辑。"""
        from app.models.digital_employee import DigitalEmployeeRepository

        # 员工 #2 无 model_id
        emp = DigitalEmployeeRepository.get_by_id(2)
        self.assertIsNotNone(emp)
        self.assertIsNone(emp.get("model_id"))

        # SQL LEFT JOIN 返回的 model_name 为 None
        model_name = emp.get("model_name")
        self.assertIsNone(model_name)

        # 模板中应使用 `emp.get('model_name') or '默认模型'`
        display_name = model_name or "默认模型"
        self.assertEqual(display_name, "默认模型",
                         "model_name 为 None 时应回退显示为'默认模型'")

    def test_model_name_has_value(self):
        """验证有 model_id 的员工 model_name 正常显示。"""
        from app.models.digital_employee import DigitalEmployeeRepository

        emp = DigitalEmployeeRepository.get_by_id(1)
        self.assertIsNotNone(emp)
        self.assertEqual(emp.get("model_name"), "测试模型")

        display_name = emp.get("model_name") or "默认模型"
        self.assertEqual(display_name, "测试模型")

    def test_skills_text_join_with_int_ids(self):
        """Bug #32 关联: 验证 skills_list 含 int ID 时的安全 join 逻辑。"""
        from app.models.skill import SkillRepository

        # 模拟 skills_list 为 int ID 数组（如 [1, 2]）
        skills_list = [1, 2]
        if skills_list and isinstance(skills_list[0], int):
            resolved = SkillRepository.resolve_by_ids(skills_list)
            skill_names = [s["name"] for s in resolved]
        else:
            skill_names = [str(s) for s in skills_list] if skills_list else []

        skills_text = "、".join(skill_names) if skill_names else "通用助手"
        self.assertIn("数据搜索", skills_text)
        self.assertIn("深度采集", skills_text)


class TestEmployeeUIResolutionEdgeCases(unittest.TestCase):
    """边界情况测试。"""

    @classmethod
    def setUpClass(cls):
        _setup_test_db()
        _seed_test_data()

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)

    def test_empty_skills(self):
        """空技能列表返回空数组。"""
        from app.models.skill import SkillRepository
        result = SkillRepository.resolve_by_ids([])
        self.assertEqual(result, [])

        names = [s["name"] for s in result]
        self.assertEqual(names, [])

    def test_nonexistent_skill_ids(self):
        """不存在的技能 ID 被静默忽略。"""
        from app.models.skill import SkillRepository
        result = SkillRepository.resolve_by_ids([999, 1000])
        self.assertEqual(result, [])

    def test_mixed_valid_invalid_ids(self):
        """混合有效/无效 ID，只返回有效的。"""
        from app.models.skill import SkillRepository
        result = SkillRepository.resolve_by_ids([1, 999])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "数据搜索")


if __name__ == "__main__":
    unittest.main()
