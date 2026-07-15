"""
system_tools.py — 系统管理类 MCP 工具处理函数

工具:
- load_skill: 加载技能
- get_system_stats: 系统概览 (v0.6.0 新增)
"""

import json as _json
from typing import Any, Dict


def _load_skill(skill_name: str) -> Dict[str, Any]:
    """加载指定技能的完整执行指令。

    根据技能类型返回不同内容：
    - prompt 型：返回完整 prompt_template（供 LLM 注入系统指令）
    - function 型：返回 function_name + function_params（供 LLM 后续调用对应工具）
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

    skill_type = skill.get("skill_type", "prompt")
    if skill_type == "prompt":
        return {
            "success": True,
            "skill_type": "prompt",
            "skill_name": skill["name"],
            "description": skill.get("description", ""),
            "content": skill.get("prompt_template", ""),
            "usage": "请将以上 content 作为你的系统指令严格遵循，完成用户的任务。",
        }
    else:  # function
        func_name = skill.get("function_name", "")
        func_params_str = skill.get("function_params", "{}")
        try:
            func_params = _json.loads(func_params_str)
        except Exception:
            func_params = {}
        return {
            "success": True,
            "skill_type": "function",
            "skill_name": skill["name"],
            "description": skill.get("description", ""),
            "function_name": func_name,
            "function_params": func_params,
            "usage": (
                f"此技能映射到 MCP 工具「{func_name}」。"
                f"请根据用户需求调用该工具，默认参数: {func_params_str}。"
            ),
        }


def _get_system_stats() -> Dict[str, Any]:
    """获取系统统计概览（v0.6.0 新增）。"""
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
