"""
skill.py — 技能 Repository

管理「技能库」的 CRUD，供管理后台和数字员工技能选择使用。
技能类型：
- prompt:  加载后注入一段 prompt 增强指令（通过 MCP load_skill 工具按需获取）
- function: 加载后映射到 MCP 工具（如 search_warehouse），LLM 通过 Function Calling 执行
"""
import json
import sqlite3
from app.models.db import get_db

SKILL_TYPES = [
    {"value": "prompt", "name": "Prompt 增强"},
    {"value": "function", "name": "Function 调用"},
]


class SkillRepository:
    """技能数据访问类 (Repository Pattern)。"""

    @staticmethod
    def get_all(page: int = 1, page_size: int = 20, skill_type: str = "") -> tuple:
        """分页查询技能列表。返回 (rows, total)。"""
        with get_db() as conn:
            conditions = []
            params = []
            if skill_type:
                conditions.append("skill_type = ?")
                params.append(skill_type)
            where = "WHERE " + " AND ".join(conditions) if conditions else ""
            total = conn.execute(
                f"SELECT COUNT(*) as cnt FROM skills {where}", params
            ).fetchone()["cnt"]
            rows = conn.execute(
                f"SELECT * FROM skills {where} ORDER BY id ASC "
                f"LIMIT ? OFFSET ?",
                (*params, page_size, (page - 1) * page_size),
            ).fetchall()
        return [dict(r) for r in rows], total

    @staticmethod
    def get_by_id(skill_id: int):
        """根据 ID 获取技能。"""
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM skills WHERE id = ?", (skill_id,)
            ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def get_by_name(name: str):
        """根据名称获取技能。"""
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM skills WHERE name = ?", (name.strip(),)
            ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def get_enabled(skill_type: str = ""):
        """获取所有启用的技能。"""
        with get_db() as conn:
            if skill_type:
                rows = conn.execute(
                    "SELECT * FROM skills WHERE is_enabled = 1 AND skill_type = ? "
                    "ORDER BY id ASC", (skill_type,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM skills WHERE is_enabled = 1 ORDER BY id ASC"
                ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def resolve_by_ids(skill_ids: list) -> list:
        """根据 ID 列表批量查询技能详情。
        返回 [{id, name, description, skill_type, prompt_template,
                function_name, function_params, is_enabled}, ...]。
        只返回启用且存在的技能。
        """
        if not skill_ids:
            return []
        with get_db() as conn:
            placeholders = ",".join("?" for _ in skill_ids)
            rows = conn.execute(
                f"SELECT * FROM skills WHERE id IN ({placeholders}) "
                f"AND is_enabled = 1 ORDER BY id ASC",
                skill_ids,
            ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def resolve_by_names(skill_names: list) -> list:
        """根据名称列表批量查询技能详情（兼容旧格式字符串标签）。
        返回 [{id, name, description, skill_type, prompt_template,
                function_name, function_params, is_enabled}, ...]。
        """
        if not skill_names:
            return []
        with get_db() as conn:
            placeholders = ",".join("?" for _ in skill_names)
            rows = conn.execute(
                f"SELECT * FROM skills WHERE name IN ({placeholders}) "
                f"AND is_enabled = 1 ORDER BY id ASC",
                skill_names,
            ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def get_skill_summaries(skill_ids: list = None, skill_names: list = None) -> list:
        """获取技能的轻量摘要列表（供 system prompt 嵌入）。
        仅返回 [{name, description}]，用于 LLM 决策是否调用 load_skill 工具。

        Args:
            skill_ids: 技能 ID 列表（新格式）
            skill_names: 技能名称列表（旧格式兼容）
        Returns:
            [{name, description}, ...] 仅返回启用且存在的技能
        """
        skills = []
        if skill_ids:
            skills = SkillRepository.resolve_by_ids(skill_ids)
        elif skill_names:
            skills = SkillRepository.resolve_by_names(skill_names)
        return [
            {"name": s["name"], "description": s.get("description", "")}
            for s in skills
        ]

    @staticmethod
    def create(name: str, description: str = "", skill_type: str = "prompt",
               prompt_template: str = "", function_name: str = "",
               function_params: str = "{}") -> int:
        """创建技能。返回新 ID 或 -1。"""
        try:
            # 校验 function_params JSON 格式
            try:
                json.loads(function_params)
            except (json.JSONDecodeError, TypeError):
                function_params = "{}"
            with get_db() as conn:
                cur = conn.execute(
                    "INSERT INTO skills (name, description, skill_type, "
                    "prompt_template, function_name, function_params) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (name.strip(), description.strip(), skill_type,
                     prompt_template.strip(), function_name.strip(), function_params),
                )
                conn.commit()
                return cur.lastrowid
        except sqlite3.IntegrityError:
            return -1

    @staticmethod
    def update(skill_id: int, name: str, description: str = "",
               skill_type: str = "prompt", prompt_template: str = "",
               function_name: str = "", function_params: str = "{}") -> bool:
        """更新技能。返回是否成功。"""
        try:
            try:
                json.loads(function_params)
            except (json.JSONDecodeError, TypeError):
                function_params = "{}"
            with get_db() as conn:
                conn.execute(
                    "UPDATE skills SET name = ?, description = ?, skill_type = ?, "
                    "prompt_template = ?, function_name = ?, function_params = ? "
                    "WHERE id = ?",
                    (name.strip(), description.strip(), skill_type,
                     prompt_template.strip(), function_name.strip(),
                     function_params, skill_id),
                )
                conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    @staticmethod
    def delete(skill_id: int):
        """删除技能。"""
        with get_db() as conn:
            conn.execute("DELETE FROM skills WHERE id = ?", (skill_id,))
            conn.commit()

    @staticmethod
    def toggle_enabled(skill_id: int) -> int:
        """切换启用/禁用状态。返回新状态 (1/0) 或 -1（不存在）。"""
        with get_db() as conn:
            row = conn.execute(
                "SELECT is_enabled FROM skills WHERE id = ?", (skill_id,)
            ).fetchone()
            if not row:
                return -1
            new_status = 0 if row["is_enabled"] == 1 else 1
            conn.execute(
                "UPDATE skills SET is_enabled = ? WHERE id = ?",
                (new_status, skill_id),
            )
            conn.commit()
            return new_status

    @staticmethod
    def get_stats() -> dict:
        """获取技能统计。"""
        with get_db() as conn:
            total = conn.execute(
                "SELECT COUNT(*) as cnt FROM skills"
            ).fetchone()["cnt"]
            enabled = conn.execute(
                "SELECT COUNT(*) as cnt FROM skills WHERE is_enabled = 1"
            ).fetchone()["cnt"]
            prompt_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM skills WHERE skill_type = 'prompt'"
            ).fetchone()["cnt"]
            function_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM skills WHERE skill_type = 'function'"
            ).fetchone()["cnt"]
        return {
            "total": total,
            "enabled": enabled,
            "prompt_count": prompt_count,
            "function_count": function_count,
        }
