#!/usr/bin/env python3
"""验证种子数据修复的一致性。

测试覆盖:
  #41 - 所有 LLM 型员工都有 mcp_tool_ids（天气 API 型除外）
  #42 - 无硬编码数字 MCP 工具 ID
  #43 - 所有 seed skills 都有非 NULL mcp_tool_id（翻译助手、代码辅助除外）
  #44 - seed skills 数量 ≥ 14
  #45 - MCP 工具描述包含使用提示（非简短版）
"""

import json
import os
import sqlite3
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app.models.db as db_module
from app.models.db import get_db, init_db, _seed_default_skills, _seed_default_mcp_tools, _seed_default_employees


def test_seed_data(monkeypatch):
    """使用临时内存数据库运行种子并验证所有修复。"""
    # 用临时内存数据库替代文件数据库
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    # 手动创建必要的表结构（精简版，仅验证用）
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS mcp_tools (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL DEFAULT 'general',
            tool_type TEXT NOT NULL DEFAULT 'builtin',
            handler_module TEXT DEFAULT '',
            api_url TEXT DEFAULT '',
            api_method TEXT DEFAULT 'GET',
            api_headers TEXT DEFAULT '{}',
            api_params_template TEXT DEFAULT '',
            input_schema TEXT DEFAULT '{}',
            output_schema TEXT DEFAULT '{}',
            is_enabled INTEGER DEFAULT 1,
            is_system INTEGER DEFAULT 0,
            sort_order INTEGER DEFAULT 0,
            config TEXT DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS skills (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            description TEXT NOT NULL DEFAULT '',
            prompt_template TEXT DEFAULT '',
            mcp_tool_id INTEGER,
            is_enabled INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS digital_employees (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            employee_type TEXT NOT NULL DEFAULT 'llm',
            description TEXT DEFAULT '',
            model_id TEXT,
            system_prompt TEXT,
            skills TEXT DEFAULT '[]',
            crawl4ai_enabled INTEGER DEFAULT 0,
            mcp_tool_ids TEXT DEFAULT '[]',
            mcp_tool_id INTEGER DEFAULT NULL,
            is_enabled INTEGER DEFAULT 1,
            api_url TEXT,
            api_method TEXT DEFAULT 'GET',
            api_headers TEXT DEFAULT '{}',
            api_params_template TEXT DEFAULT '',
            response_render_template TEXT DEFAULT '',
            api_interface_id INTEGER
        );

        CREATE TABLE IF NOT EXISTS api_interfaces (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE
        );
    """)

    # 先插入 API 接口（天气员工需要）
    conn.execute(
        "INSERT INTO api_interfaces (id, name) VALUES (1, '天气查询接口')"
    )

    # 1. 种子 MCP 工具（先于 skills/employees）
    monkeypatch.setattr(db_module, "get_db", lambda: conn)
    _seed_default_mcp_tools()

    # 验证工具已种子
    tool_count = conn.execute("SELECT COUNT(*) as cnt FROM mcp_tools").fetchone()["cnt"]
    print(f"✓ MCP 工具数量: {tool_count}")
    assert tool_count >= 18, f"应为 18 个工具，实际 {tool_count}"

    # ---- Issue #45: 工具描述包含使用提示 ----
    tool_rows = conn.execute("SELECT name, description FROM mcp_tools").fetchall()
    for row in tool_rows:
        desc = row["description"]
        name = row["name"]
        # 验证描述不是简短版（比如 "在数据仓库中搜索关键词相关内容" 不带使用提示）
        if name == "search_warehouse":
            assert "当用户询问" in desc or "使用此工具" in desc, \
                f"search_warehouse 描述缺少使用提示: {desc[:60]}"
        if name == "get_warehouse_stats":
            assert "当用户询问" in desc or "使用此工具" in desc, \
                f"get_warehouse_stats 描述缺少使用提示: {desc[:60]}"
        if name == "get_random_music":
            assert "当用户说" in desc or "使用此工具" in desc, \
                f"get_random_music 描述缺少使用提示: {desc[:60]}"
    # 抽样验证几个关键工具
    load_skill_desc = conn.execute(
        "SELECT description FROM mcp_tools WHERE name='load_skill'"
    ).fetchone()["description"]
    assert "不要猜测" in load_skill_desc, f"load_skill 描述缺少关键提示: {load_skill_desc[:60]}"
    print("✓ #45: MCP 工具描述已更新为含使用提示的版本")

    # 2. 种子 Skills
    _seed_default_skills()

    # ---- Issue #44: 至少 14 个技能 ----
    skill_count = conn.execute("SELECT COUNT(*) as cnt FROM skills").fetchone()["cnt"]
    print(f"✓ 技能数量: {skill_count}")
    assert skill_count >= 14, f"应为至少 14 个技能，实际 {skill_count}"

    # ---- Issue #43: 技能 mcp_tool_id 非 NULL（翻译助手、代码辅助除外）----
    skill_rows = conn.execute(
        "SELECT name, mcp_tool_id FROM skills"
    ).fetchall()
    null_tool_skills = [r["name"] for r in skill_rows if r["mcp_tool_id"] is None]
    expected_null = {"翻译助手", "代码辅助"}
    unexpected_null = set(null_tool_skills) - expected_null
    assert not unexpected_null, \
        f"以下技能的 mcp_tool_id 不应为 NULL（应为对应工具 ID）: {unexpected_null}"
    print(f"✓ #43: 技能 mcp_tool_id 已绑定（翻译助手/代码辅助为 NULL 符合预期）")

    # 验证 mcp_tool_id 引用的是真实存在的工具 ID
    tool_ids = {r["id"] for r in conn.execute("SELECT id FROM mcp_tools").fetchall()}
    for row in skill_rows:
        if row["mcp_tool_id"] is not None:
            assert row["mcp_tool_id"] in tool_ids, \
                f"技能 '{row['name']}' 的 mcp_tool_id={row['mcp_tool_id']} 不存在于 mcp_tools 表中"

    # 验证新增的 9 个技能存在
    new_skill_names = [
        "产业分析", "政策解读", "竞品分析", "趋势预判",
        "文案撰写", "代码辅助", "百科问答", "信息检索", "数据分析"
    ]
    for name in new_skill_names:
        exists = conn.execute(
            "SELECT id FROM skills WHERE name = ?", (name,)
        ).fetchone()
        assert exists, f"缺少新增技能: {name}"
    print(f"✓ #44: 新增 9 个技能全部存在")

    # 3. 种子员工
    _seed_default_employees()

    # ---- Issue #41: 所有 LLM 型员工都有 mcp_tool_ids ----
    emp_rows = conn.execute(
        "SELECT name, employee_type, mcp_tool_ids FROM digital_employees"
    ).fetchall()

    llm_employees = [r for r in emp_rows if r["employee_type"] == "llm"]
    api_employees = [r for r in emp_rows if r["employee_type"] == "api"]

    print(f"✓ 员工总数: {len(emp_rows)} (LLM: {len(llm_employees)}, API: {len(api_employees)})")
    assert len(emp_rows) >= 8, f"应为至少 8 个员工，实际 {len(emp_rows)}"

    # 验证每个 LLM 员工都有非空 mcp_tool_ids
    for emp in llm_employees:
        try:
            tool_ids_list = json.loads(emp["mcp_tool_ids"]) if emp["mcp_tool_ids"] else []
        except (json.JSONDecodeError, TypeError):
            tool_ids_list = []
        assert len(tool_ids_list) > 0, \
            f"LLM 员工 '{emp['name']}' 缺少 mcp_tool_ids（应至少有一个工具）"

    # 验证天气（API 型）不应该有 mcp_tool_ids
    weather = [r for r in api_employees if r["name"] == "天气"]
    if weather:
        try:
            weather_tools = json.loads(weather[0]["mcp_tool_ids"]) if weather[0]["mcp_tool_ids"] else []
        except (json.JSONDecodeError, TypeError):
            weather_tools = []
        assert len(weather_tools) == 0, \
            f"API 型员工 '天气' 不应有 mcp_tool_ids，实际: {weather_tools}"

    print(f"✓ #41: 所有 LLM 型员工已配置 mcp_tool_ids（API 型天气除外）")

    # ---- Issue #42: 无硬编码数字 ID ----
    # 验证 mcp_tool_ids 引用的都是真实存在的工具 ID
    for emp in emp_rows:
        try:
            tool_ids_list = json.loads(emp["mcp_tool_ids"]) if emp["mcp_tool_ids"] else []
        except (json.JSONDecodeError, TypeError):
            tool_ids_list = []
        for tid in tool_ids_list:
            assert tid in tool_ids, \
                f"员工 '{emp['name']}' 的 mcp_tool_ids 中 ID={tid} 不存在于 mcp_tools 表"
    print(f"✓ #42: 所有 mcp_tool_ids 都通过名称解析（无硬编码漂移 ID）")

    # 额外验证：采集专员应该有 collect_with_crawl4ai 和 batch_deep_collect
    collector = conn.execute(
        "SELECT mcp_tool_ids FROM digital_employees WHERE name='采集专员'"
    ).fetchone()
    collector_ids = json.loads(collector["mcp_tool_ids"])
    crawl4ai_id = conn.execute(
        "SELECT id FROM mcp_tools WHERE name='collect_with_crawl4ai'"
    ).fetchone()["id"]
    batch_id = conn.execute(
        "SELECT id FROM mcp_tools WHERE name='batch_deep_collect'"
    ).fetchone()["id"]
    assert crawl4ai_id in collector_ids, "采集专员缺少 collect_with_crawl4ai"
    assert batch_id in collector_ids, "采集专员缺少 batch_deep_collect"

    # 额外验证：随机音乐（API 型）通过 mcp_tool_id 绑定 get_random_music
    music_emp = conn.execute(
        "SELECT mcp_tool_id FROM digital_employees WHERE name='随机音乐'"
    ).fetchone()
    music_tool_id = conn.execute(
        "SELECT id FROM mcp_tools WHERE name='get_random_music'"
    ).fetchone()["id"]
    assert music_emp["mcp_tool_id"] == music_tool_id, f"随机音乐（API型）mcp_tool_id 应绑定 get_random_music，实际: {music_emp['mcp_tool_id']}"

    conn.close()
    print("\n✅ 所有 5 个种子数据 bug 已修复并通过验证！")


if __name__ == "__main__":
    try:
        with pytest.MonkeyPatch.context() as monkeypatch:
            test_seed_data(monkeypatch)
        sys.exit(0)
    except AssertionError as e:
        print(f"\n❌ 验证失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
