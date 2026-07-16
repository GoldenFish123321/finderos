"""
mcp_tool.py — MCP 工具 Repository (v0.10 新增)

管理 mcp_tools 表的 CRUD，以及 mcp_tool_test_logs 表。
支持按分类、状态筛选，支持工具启用/禁用、测试日志记录。
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional

from app.models.db import get_db

logger = logging.getLogger(__name__)

# 工具分类定义
MCP_TOOL_CATEGORIES = [
    {"value": "warehouse", "name": "🔍 数据仓库", "color": "#5EA3FF"},
    {"value": "collect", "name": "🔭 瞭望采集", "color": "#5FB878"},
    {"value": "employee", "name": "🤖 数字员工", "color": "#A855F7"},
    {"value": "model", "name": "🧠 AI 模型", "color": "#06B6D4"},
    {"value": "chat", "name": "💬 对话管理", "color": "#EC4899"},
    {"value": "entertainment", "name": "🎵 娱乐", "color": "#FFB800"},
    {"value": "crawl4ai", "name": "🕷️ 爬虫增强", "color": "#EF4444"},
    {"value": "system", "name": "🔧 系统管理", "color": "#6B7280"},
]

TOOL_TYPES = [
    {"value": "builtin", "name": "内置函数"},
    {"value": "api", "name": "HTTP API"},
    {"value": "crawl4ai", "name": "Crawl4ai"},
    {"value": "script", "name": "脚本工具"},
]


class MCPToolRepository:
    """MCP 工具数据访问类 (Repository Pattern)。"""

    # ── 查询 ─────────────────────────────────────────────

    @staticmethod
    def get_all(page: int = 1, page_size: int = 20,
                category: str = "", tool_type: str = "",
                is_enabled: Optional[int] = None) -> tuple:
        """分页查询 MCP 工具列表。返回 (rows, total)。"""
        with get_db() as conn:
            conditions = []
            params = []
            if category:
                conditions.append("category = ?")
                params.append(category)
            if tool_type:
                conditions.append("tool_type = ?")
                params.append(tool_type)
            if is_enabled is not None:
                conditions.append("is_enabled = ?")
                params.append(is_enabled)
            where = "WHERE " + " AND ".join(conditions) if conditions else ""
            total = conn.execute(
                f"SELECT COUNT(*) as cnt FROM mcp_tools {where}", params
            ).fetchone()["cnt"]
            rows = conn.execute(
                f"SELECT * FROM mcp_tools {where} ORDER BY category, sort_order ASC "
                f"LIMIT ? OFFSET ?",
                (*params, page_size, (page - 1) * page_size),
            ).fetchall()
        return [dict(r) for r in rows], total

    @staticmethod
    def get_by_id(tool_id: int) -> Optional[Dict[str, Any]]:
        """根据 ID 获取工具。"""
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM mcp_tools WHERE id = ?", (tool_id,)
            ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def get_by_name(name: str) -> Optional[Dict[str, Any]]:
        """根据 name 获取工具。"""
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM mcp_tools WHERE name = ?", (name.strip(),)
            ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def get_enabled(category: str = "") -> List[Dict[str, Any]]:
        """获取所有启用的工具。"""
        with get_db() as conn:
            if category:
                rows = conn.execute(
                    "SELECT * FROM mcp_tools WHERE is_enabled = 1 AND category = ? "
                    "ORDER BY category, sort_order ASC", (category,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM mcp_tools WHERE is_enabled = 1 "
                    "ORDER BY category, sort_order ASC"
                ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def get_by_ids(tool_ids: List[int]) -> List[Dict[str, Any]]:
        """根据 ID 列表批量获取工具。"""
        if not tool_ids:
            return []
        with get_db() as conn:
            placeholders = ",".join("?" for _ in tool_ids)
            rows = conn.execute(
                f"SELECT * FROM mcp_tools WHERE id IN ({placeholders}) "
                f"AND is_enabled = 1 ORDER BY category, sort_order ASC",
                tool_ids,
            ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def get_by_employee(emp_id: int) -> List[Dict[str, Any]]:
        """获取某数字员工可用的 MCP 工具列表。

        如果员工未配置 mcp_tool_ids，返回空列表（最小权限原则）。
        调用方如需兜底逻辑应自行处理。
        """
        from app.models.digital_employee import DigitalEmployeeRepository
        emp = DigitalEmployeeRepository.get_by_id(emp_id)
        if not emp:
            return []
        try:
            tool_ids = json.loads(emp.get("mcp_tool_ids", "[]"))
        except (json.JSONDecodeError, TypeError):
            tool_ids = []
        if not tool_ids:
            return []  # 最小权限：未配置则无权使用任何工具
        return MCPToolRepository.get_by_ids(tool_ids)

    @staticmethod
    def get_categories() -> List[Dict[str, Any]]:
        """获取所有有工具的分类统计。"""
        with get_db() as conn:
            rows = conn.execute(
                "SELECT category, COUNT(*) as cnt FROM mcp_tools "
                "WHERE is_enabled = 1 GROUP BY category ORDER BY category"
            ).fetchall()
        result = []
        for r in rows:
            cat_info = next(
                (c for c in MCP_TOOL_CATEGORIES if c["value"] == r["category"]),
                {"value": r["category"], "name": r["category"], "color": "#6B7280"},
            )
            result.append({**cat_info, "count": r["cnt"]})
        return result

    @staticmethod
    def get_tool_summaries(tool_ids: List[int] = None) -> List[Dict[str, Any]]:
        """获取工具摘要列表（供 system prompt 嵌入）。
        返回 [{name, display_name, description}]。
        """
        if tool_ids:
            tools = MCPToolRepository.get_by_ids(tool_ids)
        else:
            tools = MCPToolRepository.get_enabled()
        return [
            {"name": t["name"], "display_name": t["display_name"],
             "description": t.get("description", "")}
            for t in tools
        ]

    # ── 增删改 ───────────────────────────────────────────

    @staticmethod
    def create(name: str, display_name: str, description: str = "",
               category: str = "general", tool_type: str = "builtin",
               handler_module: str = "", api_url: str = "",
               api_method: str = "GET", api_headers: str = "{}",
               api_params_template: str = "",
               input_schema: str = "{}", output_schema: str = "{}",
               is_enabled: int = 1, is_system: int = 0,
               sort_order: int = 0, config: str = "{}",
               data_sources: str = "[]", transform_script: str = "",
               script_enabled: int = 0) -> int:
        """创建 MCP 工具。返回新 ID 或 -1。"""
        try:
            # 校验 JSON 字段，无效 JSON 拒绝创建
            for field_name, field_val in [
                ("input_schema", input_schema),
                ("output_schema", output_schema),
                ("api_headers", api_headers),
                ("config", config),
                ("data_sources", data_sources),
            ]:
                try:
                    json.loads(field_val)
                except (json.JSONDecodeError, TypeError):
                    logger.warning(f"创建 MCP 工具失败: {field_name} 不是有效 JSON")
                    return -1
            with get_db() as conn:
                cur = conn.execute(
                    "INSERT INTO mcp_tools (name, display_name, description, "
                    "category, tool_type, handler_module, api_url, api_method, "
                    "api_headers, api_params_template, input_schema, output_schema, "
                    "is_enabled, is_system, sort_order, config, "
                    "data_sources, transform_script, script_enabled) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (name.strip(), display_name.strip(), description.strip(),
                     category, tool_type, handler_module.strip(), api_url.strip(),
                     api_method, api_headers, api_params_template,
                     input_schema, output_schema,
                     is_enabled, is_system, sort_order, config,
                     data_sources, transform_script, script_enabled),
                )
                conn.commit()
                return cur.lastrowid
        except Exception as e:
            logger.error(f"创建 MCP 工具失败: {e}")
            return -1

    @staticmethod
    def update(tool_id: int, **kwargs) -> bool:
        """更新 MCP 工具字段。"""
        allowed = ["name", "display_name", "description", "category", "tool_type",
                    "handler_module", "api_url", "api_method", "api_headers",
                    "api_params_template", "input_schema", "output_schema",
                    "is_enabled", "is_system", "sort_order", "config",
                    "data_sources", "transform_script", "script_enabled"]
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return False
        # 自动更新 updated_at
        updates["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [tool_id]
        try:
            with get_db() as conn:
                conn.execute(
                    f"UPDATE mcp_tools SET {set_clause} WHERE id = ?", values
                )
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"更新 MCP 工具失败: {e}")
            return False

    @staticmethod
    def delete(tool_id: int) -> bool:
        """删除 MCP 工具（系统工具不可删除）。"""
        with get_db() as conn:
            row = conn.execute(
                "SELECT is_system FROM mcp_tools WHERE id = ?", (tool_id,)
            ).fetchone()
            if not row:
                return False
            if row["is_system"] == 1:
                logger.warning(f"尝试删除系统工具 ID={tool_id}，已阻止")
                return False
            conn.execute("DELETE FROM mcp_tools WHERE id = ?", (tool_id,))
            conn.commit()
            return True

    @staticmethod
    def toggle_enabled(tool_id: int) -> int:
        """切换启用/禁用。返回新状态 (0/1) 或 -1。"""
        with get_db() as conn:
            row = conn.execute(
                "SELECT is_enabled FROM mcp_tools WHERE id = ?", (tool_id,)
            ).fetchone()
            if not row:
                return -1
            new_status = 0 if row["is_enabled"] == 1 else 1
            conn.execute(
                "UPDATE mcp_tools SET is_enabled = ?, updated_at = ? WHERE id = ?",
                (new_status, time.strftime("%Y-%m-%d %H:%M:%S"), tool_id),
            )
            conn.commit()
            return new_status

    @staticmethod
    def get_count() -> int:
        """获取工具总数。"""
        with get_db() as conn:
            return conn.execute(
                "SELECT COUNT(*) as cnt FROM mcp_tools"
            ).fetchone()["cnt"]

    # ── 测试日志 ─────────────────────────────────────────

    @staticmethod
    def log_test(tool_id: int, test_params: str, test_result: str,
                 is_success: int, duration_ms: int) -> int:
        """记录一次工具测试日志。返回日志 ID。"""
        with get_db() as conn:
            cur = conn.execute(
                "INSERT INTO mcp_tool_test_logs "
                "(tool_id, test_params, test_result, is_success, duration_ms) "
                "VALUES (?, ?, ?, ?, ?)",
                (tool_id, test_params, test_result, is_success, duration_ms),
            )
            conn.commit()
            return cur.lastrowid

    @staticmethod
    def get_test_logs(tool_id: int, limit: int = 20) -> List[Dict[str, Any]]:
        """获取工具的测试日志。"""
        with get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM mcp_tool_test_logs WHERE tool_id = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (tool_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]
