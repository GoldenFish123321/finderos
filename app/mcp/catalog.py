"""Import-safe canonical catalog for builtin MCP tools."""
from __future__ import annotations

import json


def canonical_tool_records() -> list[dict]:
    from app.mcp.registry import discover_builtin_tool_definitions

    category_names = {
        "warehouse_tools": "warehouse", "collect_tools": "collect",
        "employee_tools": "employee", "model_tools": "model",
        "chat_tools": "chat", "entertainment_tools": "entertainment",
        "crawl4ai_tools": "crawl4ai", "system_tools": "system",
        "media_tools": "media",
    }
    records = []
    for order, definition in enumerate(discover_builtin_tool_definitions(), 1):
        module_name = definition["handler_module"].rsplit(".", 2)[-2]
        records.append({
            **definition,
            "display_name": definition["name"],
            "category": category_names.get(module_name, "general"),
            "sort_order": order,
        })
    return records


def canonical_tool_names() -> set[str]:
    return {record["name"] for record in canonical_tool_records()}


def upsert_builtin_tools(conn) -> int:
    """Fill partial catalogs and normalize behavior-bearing metadata by name."""
    records = canonical_tool_records()
    canonical_names = {record["name"] for record in records}

    for record in records:
        conn.execute(
            "INSERT INTO mcp_tools "
            "(name, display_name, description, category, tool_type, handler_module, "
            "input_schema, output_schema, is_enabled, is_system, sort_order, config) "
            "VALUES (?, ?, ?, ?, 'builtin', ?, ?, '{}', 1, 1, ?, '{}') "
            "ON CONFLICT(name) DO UPDATE SET "
            "description=excluded.description, category=excluded.category, "
            "handler_module=excluded.handler_module, input_schema=excluded.input_schema",
            (record["name"], record["display_name"], record["description"],
             record["category"], record["handler_module"],
             json.dumps(record["input_schema"], ensure_ascii=False), record["sort_order"]),
        )

    # 清理残留的内置工具记录：仅删除 handler_module 指向 builtin_tools 包
    # 但函数名已不存在的记录（如函数重命名后的旧自动发现残留）。
    # 保留用户自定义工具（无 handler_module 或指向其他路径）。
    stale_rows = conn.execute(
        "SELECT name FROM mcp_tools WHERE tool_type='builtin'"
        " AND handler_module LIKE 'app.mcp.builtin_tools.%'"
        " AND name NOT IN ({})".format(",".join("?" for _ in canonical_names)),
        list(canonical_names) if canonical_names else [""],
    ).fetchall()
    stale = {row["name"] for row in stale_rows}
    if stale:
        import logging
        logger = logging.getLogger(__name__)
        for name in sorted(stale):
            conn.execute(
                "DELETE FROM mcp_tools WHERE name=? AND tool_type='builtin'"
                " AND handler_module LIKE 'app.mcp.builtin_tools.%'",
                (name,),
            )
            logger.info(f"已清理残留内置工具记录: {name}")

    return len(records)
