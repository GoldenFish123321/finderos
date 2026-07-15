"""
system_tools.py — 系统管理类 MCP 工具处理函数

工具:
- load_skill: 加载技能
- get_system_stats: 系统概览 (v0.10 新增)
"""

import json as _json
from typing import Any, Dict


def _load_skill(skill_name: str) -> Dict[str, Any]:
    """加载指定技能的 prompt 模板指令。

    技能统一为 Prompt 模板，LLM 获取后按模板中的指示执行任务。
    模板中可以直接描述应使用哪些 MCP 工具及用法。
    请使用确切的技能名称，不要猜测不存在的技能。
    """
    from app.models.skill import SkillRepository
    skill = SkillRepository.get_by_name(skill_name.strip())
    if not skill:
        return {
            "success": False,
            "error": f"技能「{skill_name}」不存在",
            "hint": "请检查技能名称拼写，或使用 /tools 查看可用工具列表",
        }
    if skill.get("is_enabled") != 1:
        return {
            "success": False,
            "error": f"技能「{skill_name}」已被禁用",
        }

    return {
        "success": True,
        "skill_name": skill["name"],
        "description": skill.get("description", ""),
        "content": skill.get("prompt_template", ""),
        "usage": "请将以上 content 作为你的系统指令严格遵循，完成用户的任务。如需使用 MCP 工具，请在 content 中自行描述。",
    }


def _get_system_stats() -> Dict[str, Any]:
    """获取系统统计概览（v0.10 新增）。"""
    from app.models.db import get_db
    with get_db() as conn:
        user_count = conn.execute("SELECT COUNT(*) as cnt FROM users").fetchone()["cnt"]
        dw_count = conn.execute("SELECT COUNT(*) as cnt FROM data_warehouse").fetchone()["cnt"]
        emp_count = conn.execute("SELECT COUNT(*) as cnt FROM digital_employees WHERE is_enabled=1").fetchone()["cnt"]
        model_count = conn.execute("SELECT COUNT(*) as cnt FROM ai_models WHERE is_enabled=1").fetchone()["cnt"]
        source_count = conn.execute("SELECT COUNT(*) as cnt FROM watch_sources WHERE is_enabled=1").fetchone()["cnt"]
        conv_count = conn.execute("SELECT COUNT(*) as cnt FROM conversations").fetchone()["cnt"]

    return {
        "users": user_count,
        "data_warehouse_records": dw_count,
        "digital_employees": emp_count,
        "ai_models": model_count,
        "watch_sources": source_count,
        "conversations": conv_count,
    }
