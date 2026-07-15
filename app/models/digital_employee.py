"""
digital_employee.py — 数字化员工 Repository

支持两种类型：
- llm:  基于大语言模型（模型 + 提示词 + 技能 + Crawl4ai 可选）
- api:  基于 HTTP API（URL + 参数 + 配置）
"""
import json
import sqlite3
from app.models.db import get_db
from app.utils.security import encrypt_api_key, decrypt_api_key

EMPLOYEE_TYPES = [
    {"value": "llm", "name": "LLM 型"},
    {"value": "api", "name": "API 型"},
]


class DigitalEmployeeRepository:
    """数字化员工数据访问类 (Repository Pattern)。"""

    @staticmethod
    def get_all(page: int = 1, page_size: int = 12, employee_type: str = "") -> tuple:
        """分页查询数字员工列表。返回 (rows, total)。"""
        with get_db() as conn:
            conditions = []
            params = []
            if employee_type:
                conditions.append("employee_type = ?")
                params.append(employee_type)
            where = "WHERE " + " AND ".join(conditions) if conditions else ""
            total = conn.execute(
                f"SELECT COUNT(*) as cnt FROM digital_employees {where}", params
            ).fetchone()["cnt"]
            rows = conn.execute(
                f"SELECT d.*, m.name as model_name FROM digital_employees d "
                f"LEFT JOIN ai_models m ON d.model_id = m.id "
                f"{where} ORDER BY d.id ASC "
                f"LIMIT ? OFFSET ?",
                (*params, page_size, (page - 1) * page_size),
            ).fetchall()
        # 解密 api_config 中的敏感字段
        result = []
        for row in rows:
            row_dict = dict(row)
            row_dict = _decrypt_employee_secrets(row_dict)
            result.append(row_dict)
        return result, total

    @staticmethod
    def get_by_id(emp_id: int):
        """根据 ID 获取数字员工。"""
        with get_db() as conn:
            row = conn.execute(
                "SELECT d.*, m.name as model_name FROM digital_employees d "
                "LEFT JOIN ai_models m ON d.model_id = m.id "
                "WHERE d.id = ?",
                (emp_id,),
            ).fetchone()
        if row:
            row_dict = dict(row)
            return _decrypt_employee_secrets(row_dict)
        return None

    @staticmethod
    def get_enabled():
        """获取所有启用的数字员工（供前端 @ 选择器使用）。"""
        with get_db() as conn:
            rows = conn.execute(
                "SELECT d.*, m.name as model_name FROM digital_employees d "
                "LEFT JOIN ai_models m ON d.model_id = m.id "
                "WHERE d.is_enabled = 1 ORDER BY d.id ASC"
            ).fetchall()
        return [_decrypt_employee_secrets(dict(r)) for r in rows]

    @staticmethod
    def create(name: str, employee_type: str = "llm", description: str = "",
               model_id: int = None, system_prompt: str = "",
               skills: str = "[]", crawl4ai_enabled: int = 0,
               mcp_tool_ids: str = "[]",
               api_url: str = "", api_method: str = "GET",
               api_headers: str = "{}", api_params_template: str = "",
               response_render_template: str = "",
               api_secret: str = "", api_interface_id: int = None) -> int:
        """创建数字员工。返回新 ID 或 -1。"""
        try:
            # 加密 API 型员工的敏感凭证
            encrypted_secret = encrypt_api_key(api_secret.strip()) if api_secret else ""
            with get_db() as conn:
                cur = conn.execute(
                    "INSERT INTO digital_employees (name, employee_type, description, "
                    "model_id, system_prompt, skills, crawl4ai_enabled, mcp_tool_ids, "
                    "api_url, api_method, api_headers, api_params_template, "
                    "response_render_template, api_secret, api_interface_id) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (name.strip(), employee_type, description,
                     model_id, system_prompt, skills, crawl4ai_enabled, mcp_tool_ids,
                     api_url.strip(), api_method, api_headers, api_params_template,
                     response_render_template, encrypted_secret, api_interface_id),
                )
                conn.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return -1

    @staticmethod
    def update(emp_id: int, name: str, employee_type: str = "llm", description: str = "",
               model_id: int = None, system_prompt: str = "",
               skills: str = "[]", crawl4ai_enabled: int = 0,
               mcp_tool_ids: str = "[]",
               api_url: str = "", api_method: str = "GET",
               api_headers: str = "{}", api_params_template: str = "",
               response_render_template: str = "",
               api_secret: str = "", api_interface_id: int = None) -> bool:
        """更新数字员工。api_secret 为空时保留旧值。"""
        try:
            if not api_secret:
                existing = DigitalEmployeeRepository.get_by_id(emp_id)
                if existing:
                    api_secret = existing.get("api_secret", "")
            encrypted_secret = encrypt_api_key(api_secret.strip()) if api_secret else ""
            with get_db() as conn:
                conn.execute(
                    "UPDATE digital_employees SET name=?, employee_type=?, description=?, "
                    "model_id=?, system_prompt=?, skills=?, crawl4ai_enabled=?, mcp_tool_ids=?, "
                    "api_url=?, api_method=?, api_headers=?, api_params_template=?, "
                    "response_render_template=?, api_secret=?, api_interface_id=? WHERE id=?",
                    (name.strip(), employee_type, description,
                     model_id, system_prompt, skills, crawl4ai_enabled, mcp_tool_ids,
                     api_url.strip(), api_method, api_headers, api_params_template,
                     response_render_template, encrypted_secret, api_interface_id, emp_id),
                )
                conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    @staticmethod
    def delete(emp_id: int) -> bool:
        """删除数字员工。"""
        with get_db() as conn:
            cursor = conn.execute("DELETE FROM digital_employees WHERE id = ?", (emp_id,))
            conn.commit()
            return cursor.rowcount > 0

    @staticmethod
    def toggle_enabled(emp_id: int) -> int:
        """切换启用/禁用状态。返回新状态 (0/1) 或 -1。"""
        with get_db() as conn:
            row = conn.execute(
                "SELECT is_enabled FROM digital_employees WHERE id = ?", (emp_id,)
            ).fetchone()
            if not row:
                return -1
            new_status = 0 if row["is_enabled"] == 1 else 1
            conn.execute(
                "UPDATE digital_employees SET is_enabled = ? WHERE id = ?",
                (new_status, emp_id),
            )
            conn.commit()
            return new_status

    @staticmethod
    def get_stats() -> dict:
        """获取数字员工统计。"""
        with get_db() as conn:
            total = conn.execute(
                "SELECT COUNT(*) as cnt FROM digital_employees"
            ).fetchone()["cnt"]
            enabled = conn.execute(
                "SELECT COUNT(*) as cnt FROM digital_employees WHERE is_enabled = 1"
            ).fetchone()["cnt"]
            llm_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM digital_employees WHERE employee_type = 'llm'"
            ).fetchone()["cnt"]
            api_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM digital_employees WHERE employee_type = 'api'"
            ).fetchone()["cnt"]
            return {
                "total": total,
                "enabled": enabled,
                "llm_count": llm_count,
                "api_count": api_count,
            }

    @staticmethod
    def get_count() -> int:
        """获取数字员工总数。"""
        with get_db() as conn:
            return conn.execute(
                "SELECT COUNT(*) as cnt FROM digital_employees"
            ).fetchone()["cnt"]


# ── 内部辅助 ─────────────────────────────────────────────────

def _decrypt_employee_secrets(row_dict: dict) -> dict:
    """解密员工行中的敏感字段（api_secret）。"""
    if "api_secret" in row_dict and row_dict["api_secret"]:
        row_dict["api_secret"] = decrypt_api_key(row_dict["api_secret"])
    return row_dict
