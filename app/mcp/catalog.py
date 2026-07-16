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
    return len(records)
