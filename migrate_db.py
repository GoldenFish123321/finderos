#!/usr/bin/env python3
"""
migrate_db.py — 数据库迁移脚本

向后兼容地为现有数据库添加新列/新表，不破坏已有数据。
在项目根目录运行：python migrate_db.py

迁移历史:
  v0.2  — 添加 ai_models.total_tokens (Token 累加统计)
  v0.2  — 添加 audit_logs 表 (操作审计日志)
  v0.2  — 添加安全相关索引
  v0.2  — 添加 data_warehouse 独立表 + URL 去重索引
  v0.5  — 添加 conversations / conversation_messages 表
  v0.4  — 添加 digital_employees 表
  v0.5  — 添加 data_warehouse_fts 虚拟表 + 同步触发器
  v0.6  — 添加 watch_sources.schedule_interval 列
  v0.9  — 添加 api_interfaces 表与 digital_employees.api_interface_id
  v0.7  — 添加 skills 技能库表
  v0.10 — 添加 mcp_tools MCP工具注册表 + mcp_tool_test_logs
  v0.10 — 添加 skills.mcp_tool_id / digital_employees.mcp_tool_ids
  v0.11 — 迁移旧 crawl4ai_enabled=1 员工的权限到 mcp_tool_ids
  v1.3.5 — 为 conversation_messages 添加 is_sensitive / review_status 列（Issue #18）

Usage:
  python migrate_db.py              # 执行待处理迁移
  python migrate_db.py --status     # 查看迁移状态
"""

import json
import logging
import os
import re
import sqlite3
import sys

# 将项目根目录加入 Python 路径
sys.path.insert(0, os.path.dirname(__file__))

from app.models.db import DB_PATH, init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("migrate")


def run_migrations():
    """执行所有待处理的迁移。"""
    logger.info(f"数据库路径: {DB_PATH}")

    if not os.path.exists(DB_PATH):
        logger.info("数据库文件不存在，调用 init_db() 全量初始化...")
        init_db()
        logger.info("✅ 全量初始化完成")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    migrations = [
        # v0.2: ai_models 新增 total_tokens 列
        {
            "name": "add_ai_models_total_tokens",
            "sql": "ALTER TABLE ai_models ADD COLUMN total_tokens INTEGER DEFAULT 0",
            "check": lambda c: _column_exists(c, "ai_models", "total_tokens"),
        },
        # v0.2: 审计日志表
        {
            "name": "create_audit_logs",
            "sql": """
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    action      TEXT NOT NULL,
                    username    TEXT DEFAULT '',
                    target      TEXT DEFAULT '',
                    detail      TEXT DEFAULT '',
                    client_ip   TEXT DEFAULT '',
                    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """,
            "check": lambda c: _table_exists(c, "audit_logs"),
        },
        # v0.2: 审计日志索引
        {
            "name": "idx_audit_logs_action",
            "sql": "CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action)",
            "check": lambda c: _index_exists(c, "idx_audit_logs_action"),
        },
        {
            "name": "idx_audit_logs_username",
            "sql": "CREATE INDEX IF NOT EXISTS idx_audit_logs_username ON audit_logs(username)",
            "check": lambda c: _index_exists(c, "idx_audit_logs_username"),
        },
        {
            "name": "idx_audit_logs_created",
            "sql": "CREATE INDEX IF NOT EXISTS idx_audit_logs_created ON audit_logs(created_at)",
            "check": lambda c: _index_exists(c, "idx_audit_logs_created"),
        },
        # v0.2.x: 数据仓库无 link 记录去重索引（防止并发竞态写入重复数据）
        {
            "name": "idx_dw_title_source",
            "sql": "CREATE UNIQUE INDEX IF NOT EXISTS idx_dw_title_source ON data_warehouse(title, source_name) WHERE (link IS NULL OR link = '')",
            "check": lambda c: _index_exists(c, "idx_dw_title_source"),
        },
        # v0.5: 对话管理表
        {
            "name": "create_conversations",
            "sql": """
                CREATE TABLE IF NOT EXISTS conversations (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    title       TEXT DEFAULT '新对话',
                    username    TEXT DEFAULT '',
                    model_id    INTEGER DEFAULT NULL,
                    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (model_id) REFERENCES ai_models(id) ON DELETE SET NULL
                )
            """,
            "check": lambda c: _table_exists(c, "conversations"),
        },
        {
            "name": "create_conversation_messages",
            "sql": """
                CREATE TABLE IF NOT EXISTS conversation_messages (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id INTEGER NOT NULL,
                    role            TEXT NOT NULL,
                    content         TEXT DEFAULT '',
                    token_count     INTEGER DEFAULT 0,
                    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                )
            """,
            "check": lambda c: _table_exists(c, "conversation_messages"),
        },
        {
            "name": "idx_conv_msgs_conv",
            "sql": "CREATE INDEX IF NOT EXISTS idx_conv_msgs_conv ON conversation_messages(conversation_id)",
            "check": lambda c: _index_exists(c, "idx_conv_msgs_conv"),
        },
        # v0.4: 数字化员工表
        {
            "name": "create_digital_employees",
            "sql": """
                CREATE TABLE IF NOT EXISTS digital_employees (
                    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                    name                    TEXT NOT NULL,
                    employee_type           TEXT NOT NULL DEFAULT 'llm',
                    description             TEXT DEFAULT '',
                    model_id                INTEGER DEFAULT NULL,
                    system_prompt           TEXT DEFAULT '',
                    skills                  TEXT DEFAULT '[]',
                    crawl4ai_enabled        INTEGER DEFAULT 0,
                    api_url                 TEXT DEFAULT '',
                    api_method              TEXT DEFAULT 'GET',
                    api_headers             TEXT DEFAULT '{}',
                    api_params_template     TEXT DEFAULT '',
                    response_render_template TEXT DEFAULT '',
                    api_secret              TEXT DEFAULT '',
                    is_enabled              INTEGER DEFAULT 1,
                    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (model_id) REFERENCES ai_models(id) ON DELETE SET NULL
                )
            """,
            "check": lambda c: _table_exists(c, "digital_employees"),
        },
        # v0.5: FTS5 全文检索虚拟表 + 同步触发器
        {
            "name": "create_data_warehouse_fts",
            "sql": """
                CREATE VIRTUAL TABLE IF NOT EXISTS data_warehouse_fts USING fts5(
                    title, summary, source_name, content=data_warehouse,
                    content_rowid=id
                )
            """,
            "check": lambda c: _table_exists(c, "data_warehouse_fts"),
        },
        {
            "name": "dw_fts_insert_trigger",
            "sql": """
                CREATE TRIGGER IF NOT EXISTS dw_fts_insert AFTER INSERT ON data_warehouse
                BEGIN
                    INSERT INTO data_warehouse_fts(rowid, title, summary, source_name)
                    VALUES (new.id, new.title, new.summary, new.source_name);
                END
            """,
            "check": lambda c: _trigger_exists(c, "dw_fts_insert"),
        },
        {
            "name": "dw_fts_delete_trigger",
            "sql": """
                CREATE TRIGGER IF NOT EXISTS dw_fts_delete AFTER DELETE ON data_warehouse
                BEGIN
                    INSERT INTO data_warehouse_fts(data_warehouse_fts, rowid, title, summary, source_name)
                    VALUES ('delete', old.id, old.title, old.summary, old.source_name);
                END
            """,
            "check": lambda c: _trigger_exists(c, "dw_fts_delete"),
        },
        {
            "name": "dw_fts_update_trigger",
            "sql": """
                CREATE TRIGGER IF NOT EXISTS dw_fts_update AFTER UPDATE ON data_warehouse
                BEGIN
                    INSERT INTO data_warehouse_fts(data_warehouse_fts, rowid, title, summary, source_name)
                    VALUES ('delete', old.id, old.title, old.summary, old.source_name);
                    INSERT INTO data_warehouse_fts(rowid, title, summary, source_name)
                    VALUES (new.id, new.title, new.summary, new.source_name);
                END
            """,
            "check": lambda c: _trigger_exists(c, "dw_fts_update"),
        },
        # v0.6: 瞭望源定时采集间隔
        {
            "name": "add_watch_sources_schedule_interval",
            "sql": "ALTER TABLE watch_sources ADD COLUMN schedule_interval INTEGER DEFAULT 0",
            "check": lambda c: _column_exists(c, "watch_sources", "schedule_interval"),
        },
        # v0.7: 技能库表
        {
            "name": "create_skills",
            "sql": """
                CREATE TABLE IF NOT EXISTS skills (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    name            TEXT UNIQUE NOT NULL,
                    description     TEXT DEFAULT '',
                    skill_type      TEXT NOT NULL DEFAULT 'prompt',
                    prompt_template TEXT DEFAULT '',
                    function_name   TEXT DEFAULT '',
                    function_params TEXT DEFAULT '{}',
                    is_enabled      INTEGER DEFAULT 1,
                    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """,
            "check": lambda c: _table_exists(c, "skills"),
        },
        # v0.9: 接口管理模块
        {
            "name": "create_api_interfaces",
            "sql": """
                CREATE TABLE IF NOT EXISTS api_interfaces (
                    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
                    name                     TEXT UNIQUE NOT NULL,
                    description              TEXT DEFAULT '',
                    api_url                  TEXT NOT NULL,
                    api_method               TEXT DEFAULT 'GET',
                    api_headers              TEXT DEFAULT '{}',
                    api_params_template      TEXT DEFAULT '',
                    response_render_template TEXT DEFAULT '',
                    api_secret               TEXT DEFAULT '',
                    is_enabled               INTEGER DEFAULT 1,
                    sort_order               INTEGER DEFAULT 0,
                    created_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """,
            "check": lambda c: _table_exists(c, "api_interfaces"),
        },
        {
            "name": "add_digital_employees_api_interface_id",
            "sql": "ALTER TABLE digital_employees ADD COLUMN api_interface_id INTEGER DEFAULT NULL",
            "check": lambda c: _column_exists(c, "digital_employees", "api_interface_id"),
        },
        {
            "name": "idx_api_interfaces_enabled",
            "sql": "CREATE INDEX IF NOT EXISTS idx_api_interfaces_enabled ON api_interfaces(is_enabled)",
            "check": lambda c: _index_exists(c, "idx_api_interfaces_enabled"),
        },
        {
            "name": "idx_api_interfaces_name",
            "sql": "CREATE INDEX IF NOT EXISTS idx_api_interfaces_name ON api_interfaces(name)",
            "check": lambda c: _index_exists(c, "idx_api_interfaces_name"),
        },
        {
            "name": "idx_digital_employees_api_interface",
            "sql": "CREATE INDEX IF NOT EXISTS idx_digital_employees_api_interface ON digital_employees(api_interface_id)",
            "check": lambda c: _index_exists(c, "idx_digital_employees_api_interface"),
        },
        # v0.10: MCP 工具注册表
        {
            "name": "create_mcp_tools",
            "sql": """
                CREATE TABLE IF NOT EXISTS mcp_tools (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    name            TEXT UNIQUE NOT NULL,
                    display_name    TEXT NOT NULL,
                    description     TEXT DEFAULT '',
                    category        TEXT DEFAULT 'general',
                    tool_type       TEXT DEFAULT 'builtin',
                    handler_module  TEXT DEFAULT '',
                    api_url         TEXT DEFAULT '',
                    api_method      TEXT DEFAULT 'GET',
                    api_headers     TEXT DEFAULT '{}',
                    api_params_template TEXT DEFAULT '',
                    input_schema    TEXT DEFAULT '{}',
                    output_schema   TEXT DEFAULT '{}',
                    is_enabled      INTEGER DEFAULT 1,
                    is_system       INTEGER DEFAULT 0,
                    sort_order      INTEGER DEFAULT 0,
                    config          TEXT DEFAULT '{}',
                    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """,
            "check": lambda c: _table_exists(c, "mcp_tools"),
        },
        # v0.10: MCP 工具测试日志表
        {
            "name": "create_mcp_tool_test_logs",
            "sql": """
                CREATE TABLE IF NOT EXISTS mcp_tool_test_logs (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    tool_id         INTEGER NOT NULL,
                    test_params     TEXT DEFAULT '{}',
                    test_result     TEXT DEFAULT '',
                    is_success      INTEGER DEFAULT 0,
                    duration_ms     INTEGER DEFAULT 0,
                    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (tool_id) REFERENCES mcp_tools(id) ON DELETE CASCADE
                )
            """,
            "check": lambda c: _table_exists(c, "mcp_tool_test_logs"),
        },
        # v0.10: skills 新增 mcp_tool_id 列
        {
            "name": "add_skills_mcp_tool_id",
            "sql": "ALTER TABLE skills ADD COLUMN mcp_tool_id INTEGER DEFAULT NULL REFERENCES mcp_tools(id) ON DELETE SET NULL",
            "check": lambda c: _column_exists(c, "skills", "mcp_tool_id"),
        },
        # v0.10: digital_employees 新增 mcp_tool_ids 列
        {
            "name": "add_digital_employees_mcp_tool_ids",
            "sql": "ALTER TABLE digital_employees ADD COLUMN mcp_tool_ids TEXT DEFAULT '[]'",
            "check": lambda c: _column_exists(c, "digital_employees", "mcp_tool_ids"),
        },
        # v0.10: MCP 工具种子数据（18 个内置工具）
        {
            "name": "seed_mcp_tools_v042",
            "check": _check_mcp_catalog_complete,
            "run": _seed_mcp_tools,
        },
        # v0.11: 将旧 crawl4ai_enabled=1 员工的爬虫权限迁移到 mcp_tool_ids
        {
            "name": "migrate_crawl4ai_to_mcp_tool_ids_v043",
            "check": _check_crawl4ai_migrated,
            "run": _migrate_crawl4ai_to_mcp_tool_ids,
        },
        # v0.10: 旧 TAG 迁移 — 将员工 skills 字符串数组迁移为 Skill ID 数组
        {
            "name": "migrate_legacy_tags_to_skills_v042",
            "check": _check_legacy_tags_migrated,
            "run": _migrate_legacy_tags_to_skills,
        },
        {
            "name": "migrate_crawl4ai_permissions_v100",
            "check": _check_crawl4ai_permissions_migrated,
            "run": _migrate_crawl4ai_permissions,
        },
        # v1.3.5 Issue #18: conversation_messages 添加敏感标记和审核状态列
        {
            "name": "add_conversation_messages_is_sensitive",
            "sql": "ALTER TABLE conversation_messages ADD COLUMN is_sensitive INTEGER DEFAULT 0",
            "check": lambda c: _column_exists(c, "conversation_messages", "is_sensitive"),
        },
        {
            "name": "add_conversation_messages_review_status",
            "sql": "ALTER TABLE conversation_messages ADD COLUMN review_status TEXT DEFAULT 'pending'",
            "check": lambda c: _column_exists(c, "conversation_messages", "review_status"),
        },
        {
            "name": "idx_conv_msgs_sensitive",
            "sql": "CREATE INDEX IF NOT EXISTS idx_conv_msgs_sensitive ON conversation_messages(is_sensitive)",
            "check": lambda c: _index_exists(c, "idx_conv_msgs_sensitive"),
        },
        {
            "name": "idx_conv_msgs_review",
            "sql": "CREATE INDEX IF NOT EXISTS idx_conv_msgs_review ON conversation_messages(review_status)",
            "check": lambda c: _index_exists(c, "idx_conv_msgs_review"),
        },
    ]

    applied = 0
    skipped = 0

    for m in migrations:
        try:
            if m["check"](conn):
                logger.info(f"⏭️  跳过（已存在）: {m['name']}")
                skipped += 1
                continue
            # 支持两种迁移类型：SQL 语句 或 run 函数
            if "run" in m:
                m["run"](conn)
            else:
                conn.execute(m["sql"])
            conn.commit()
            logger.info(f"✅ 已应用: {m['name']}")
            applied += 1
        except Exception as e:
            logger.warning(f"⚠️  失败: {m['name']} — {e}")

    conn.close()
    logger.info(f"迁移完成: {applied} 已应用, {skipped} 已跳过")


def _table_exists(conn, table_name: str) -> bool:
    """检查表是否存在。"""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    """检查列是否存在。"""
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', table_name):
        raise ValueError(f"非法表名: {table_name}")
    if not _table_exists(conn, table_name):
        return False
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(r["name"] == column_name for r in rows)


def _index_exists(conn, index_name: str) -> bool:
    """检查索引是否存在。"""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
        (index_name,),
    ).fetchone()
    return row is not None


def _trigger_exists(conn, trigger_name: str) -> bool:
    """检查触发器是否存在。"""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='trigger' AND name=?",
        (trigger_name,),
    ).fetchone()
    return row is not None


def _seed_mcp_tools(conn):
    """v0.10: 向 mcp_tools 表插入 18 个内置工具种子数据。"""
    from app.mcp.catalog import upsert_builtin_tools
    count = upsert_builtin_tools(conn)
    logger.info(f"已同步 {count} 个 MCP 工具规范记录")
    return
    import json as _json

    tools = [
        # ── 数据仓库类 (4) ──
        {
            "name": "search_warehouse", "display_name": "数据仓库搜索",
            "category": "warehouse", "tool_type": "builtin",
            "handler_module": "app.mcp.builtin_tools.warehouse_tools._search_warehouse",
            "description": "在瞭望与问数系统的数据仓库中搜索关键词相关的内容。当用户询问「有没有关于XX的数据」「搜索XX」「查找XX」「帮我找XX」等问题时使用此工具。不要用于获取最新数据或统计信息（请使用其他专用工具）。",
            "input_schema": _json.dumps({
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "搜索关键词，从用户问题中提取的核心搜索词"},
                    "limit": {"type": "integer", "description": "返回结果数量上限，默认10", "default": 10},
                },
                "required": ["keyword"],
            }, ensure_ascii=False),
            "is_enabled": 1, "is_system": 1, "sort_order": 1,
        },
        {
            "name": "get_recent_warehouse_data", "display_name": "最新数据查询",
            "category": "warehouse", "tool_type": "builtin",
            "handler_module": "app.mcp.builtin_tools.warehouse_tools._get_recent_warehouse_data",
            "description": "获取数据仓库中最新入库的数据记录。当用户询问「最新数据」「最近有什么」「看看数据仓库」「浏览数据」时使用此工具。也适用于用户没有明确关键词但想了解数据仓库内容时。",
            "input_schema": _json.dumps({
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "返回记录数，默认10", "default": 10},
                },
            }, ensure_ascii=False),
            "is_enabled": 1, "is_system": 1, "sort_order": 2,
        },
        {
            "name": "get_warehouse_stats", "display_name": "数据统计",
            "category": "warehouse", "tool_type": "builtin",
            "handler_module": "app.mcp.builtin_tools.warehouse_tools._get_warehouse_stats",
            "description": "获取数据仓库的统计概况，包括总记录数、已深度采集数、来源分布等。当用户询问「有多少数据」「数据统计」「数据概况」「数据分布」时使用此工具。",
            "input_schema": _json.dumps({"type": "object", "properties": {}}, ensure_ascii=False),
            "is_enabled": 1, "is_system": 1, "sort_order": 3,
        },
        {
            "name": "search_warehouse_fulltext", "display_name": "全文检索(FTS5)",
            "category": "warehouse", "tool_type": "builtin",
            "handler_module": "app.mcp.builtin_tools.warehouse_tools._search_warehouse_fulltext",
            "description": "使用 FTS5 全文搜索引擎在数据仓库中进行高级全文检索。比普通关键词搜索更精确，支持布尔表达式和短语匹配。当用户需要精确查找某段文字或使用高级搜索语法时使用此工具。",
            "input_schema": _json.dumps({
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "FTS5 搜索查询，支持布尔表达式如「AI AND 搜索」"},
                    "limit": {"type": "integer", "description": "返回结果数量上限，默认20", "default": 20},
                },
                "required": ["query"],
            }, ensure_ascii=False),
            "is_enabled": 1, "is_system": 1, "sort_order": 4,
        },

        # ── 数据采集类 (3) ──
        {
            "name": "collect_web_data", "display_name": "全网采集",
            "category": "collect", "tool_type": "builtin",
            "handler_module": "app.mcp.builtin_tools.collect_tools._collect_web_data",
            "description": "执行全网瞭望数据采集任务，从配置的瞭望源（如百度新闻、搜狗新闻等）搜索指定关键词。当用户要求「采集关于XX的新闻」「帮我在网上搜索XX」「瞭望一下XX」时使用此工具。注意：这是一个批量采集工具，不是搜索数据仓库已有内容。",
            "input_schema": _json.dumps({
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "采集关键词"},
                    "source_ids": {
                        "type": "array", "items": {"type": "integer"},
                        "description": "瞭望源 ID 列表，留空则使用所有启用的瞭望源",
                    },
                },
                "required": ["keyword"],
            }, ensure_ascii=False),
            "is_enabled": 1, "is_system": 1, "sort_order": 10,
        },
        {
            "name": "deep_collect_url", "display_name": "深度采集URL",
            "category": "collect", "tool_type": "builtin",
            "handler_module": "app.mcp.builtin_tools.collect_tools._deep_collect_url",
            "description": "对指定网页 URL 进行深度内容采集，提取文章正文、标题等结构化内容。当用户提供具体URL并要求「深度采集」「抓取这个网页」「提取文章内容」「帮我看看这个链接」时使用。仅用于采集单个 URL 的详细内容，不是搜索引擎。",
            "input_schema": _json.dumps({
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "要深度采集的目标网页 URL（必须是完整 HTTP/HTTPS 链接）"},
                },
                "required": ["url"],
            }, ensure_ascii=False),
            "is_enabled": 1, "is_system": 1, "sort_order": 11,
        },
        {
            "name": "list_watch_sources", "display_name": "瞭望源列表",
            "category": "collect", "tool_type": "builtin",
            "handler_module": "app.mcp.builtin_tools.collect_tools._list_watch_sources",
            "description": "列出系统中所有已启用的瞭望源（数据采集源）。当用户询问「有哪些采集源」「瞭望源列表」「从哪些网站采集数据」时使用此工具。",
            "input_schema": _json.dumps({"type": "object", "properties": {}}, ensure_ascii=False),
            "is_enabled": 1, "is_system": 1, "sort_order": 12,
        },

        # ── 数字员工类 (2) ──
        {
            "name": "list_digital_employees", "display_name": "数字员工列表",
            "category": "employee", "tool_type": "builtin",
            "handler_module": "app.mcp.builtin_tools.employee_tools._list_digital_employees",
            "description": "列出系统中所有可用的数字员工。当用户询问「有哪些数字员工」「可以用哪些助手」「@谁」或不确定该调用哪个员工时使用。",
            "input_schema": _json.dumps({"type": "object", "properties": {}}, ensure_ascii=False),
            "is_enabled": 1, "is_system": 1, "sort_order": 20,
        },
        {
            "name": "invoke_digital_employee", "display_name": "调用数字员工",
            "category": "employee", "tool_type": "builtin",
            "handler_module": "app.mcp.builtin_tools.employee_tools._invoke_digital_employee",
            "description": "调用指定的数字员工执行任务。支持按名称或 ID 查找员工，将用户消息转发给该员工并返回执行结果。当用户想委托特定员工完成某项工作时使用此工具。",
            "input_schema": _json.dumps({
                "type": "object",
                "properties": {
                    "employee_name": {"type": "string", "description": "数字员工名称或 ID"},
                    "message": {"type": "string", "description": "要发送给该员工的消息内容"},
                },
                "required": ["employee_name", "message"],
            }, ensure_ascii=False),
            "is_enabled": 1, "is_system": 1, "sort_order": 21,
        },

        # ── AI 模型类 (2) ──
        {
            "name": "list_ai_models", "display_name": "AI模型列表",
            "category": "model", "tool_type": "builtin",
            "handler_module": "app.mcp.builtin_tools.model_tools._list_ai_models",
            "description": "列出系统中所有已启用的 AI 模型，包括模型名称、提供商、分类和默认状态。当用户询问「有哪些AI模型」「当前可用模型」「切换模型」时使用此工具。",
            "input_schema": _json.dumps({"type": "object", "properties": {}}, ensure_ascii=False),
            "is_enabled": 1, "is_system": 1, "sort_order": 30,
        },
        {
            "name": "get_default_model", "display_name": "获取默认模型",
            "category": "model", "tool_type": "builtin",
            "handler_module": "app.mcp.builtin_tools.model_tools._get_default_model",
            "description": "获取当前系统默认的 AI 模型信息。当用户询问「当前用的是什么模型」「默认模型是什么」时使用此工具。",
            "input_schema": _json.dumps({"type": "object", "properties": {}}, ensure_ascii=False),
            "is_enabled": 1, "is_system": 1, "sort_order": 31,
        },

        # ── 对话管理类 (2) ──
        {
            "name": "list_conversations", "display_name": "对话历史",
            "category": "chat", "tool_type": "builtin",
            "handler_module": "app.mcp.builtin_tools.chat_tools._list_conversations",
            "description": "列出用户的历史对话记录。当用户询问「之前的对话」「对话历史」「我之前的提问」时使用此工具。",
            "input_schema": _json.dumps({
                "type": "object",
                "properties": {
                    "username": {"type": "string", "description": "用户名（由系统自动填充）"},
                    "limit": {"type": "integer", "description": "返回数量上限，默认20", "default": 20},
                },
            }, ensure_ascii=False),
            "is_enabled": 1, "is_system": 1, "sort_order": 40,
        },
        {
            "name": "get_conversation_messages", "display_name": "对话消息",
            "category": "chat", "tool_type": "builtin",
            "handler_module": "app.mcp.builtin_tools.chat_tools._get_conversation_messages",
            "description": "获取指定对话的完整消息历史。当用户指定对话ID要求「查看那个对话」「回顾之前的聊天」时使用。",
            "input_schema": _json.dumps({
                "type": "object",
                "properties": {
                    "conversation_id": {"type": "integer", "description": "对话ID"},
                    "limit": {"type": "integer", "description": "返回消息数量上限", "default": 20},
                    "username": {"type": "string", "description": "当前用户名（由系统自动填充，用于所有权验证）"},
                },
                "required": ["conversation_id"],
            }, ensure_ascii=False),
            "is_enabled": 1, "is_system": 1, "sort_order": 41,
        },

        # ── 娱乐类 (1) ──
        {
            "name": "get_random_music", "display_name": "随机音乐",
            "category": "entertainment", "tool_type": "builtin",
            "handler_module": "app.mcp.builtin_tools.entertainment_tools._get_random_music",
            "description": "随机推荐一首歌曲。从网易云音乐热歌榜中随机选取一首，返回歌曲名、歌手、封面图和试听链接。当用户说「来首歌」「随机音乐」「推荐一首歌」「放首歌」「来点音乐」时使用此工具。注意：此工具直接返回歌曲数据，调用后应基于数据向用户展示歌曲信息。",
            "input_schema": _json.dumps({"type": "object", "properties": {}}, ensure_ascii=False),
            "is_enabled": 1, "is_system": 1, "sort_order": 50,
        },

        # ── Crawl4ai 爬虫增强类 (2) ──
        {
            "name": "collect_with_crawl4ai", "display_name": "Crawl4ai智能采集",
            "category": "crawl4ai", "tool_type": "builtin",
            "handler_module": "app.mcp.builtin_tools.crawl4ai_tools._deep_collect_url",
            "description": "使用 Crawl4ai 智能爬虫引擎对指定 URL 进行深度网页内容采集。替代旧的 crawl4ai_enabled 复选框功能，支持自动检测页面结构并提取正文。优先使用 crawl4ai 引擎，不可用时回退到标准采集。当用户提供 URL 并要求「用 crawl4ai 采集」「智能爬取这个网页」时使用。",
            "input_schema": _json.dumps({
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "要采集的目标网页 URL"},
                    "extract_mode": {"type": "string", "description": "提取模式: auto/markdown/text", "default": "auto"},
                },
                "required": ["url"],
            }, ensure_ascii=False),
            "is_enabled": 1, "is_system": 1, "sort_order": 60,
        },
        {
            "name": "batch_deep_collect", "display_name": "批量深度采集",
            "category": "crawl4ai", "tool_type": "builtin",
            "handler_module": "app.mcp.builtin_tools.crawl4ai_tools._batch_deep_collect_url",
            "description": "批量对多个 URL 进行深度内容采集。一次性提交多个链接，系统逐一采集并汇总结果。当用户需要「批量抓取这些网页」「同时采集这几个链接」时使用此工具。",
            "input_schema": _json.dumps({
                "type": "object",
                "properties": {
                    "urls": {
                        "type": "array", "items": {"type": "string"},
                        "description": "要采集的 URL 列表",
                    },
                    "extract_mode": {"type": "string", "description": "提取模式: auto/markdown/text", "default": "auto"},
                },
                "required": ["urls"],
            }, ensure_ascii=False),
            "is_enabled": 1, "is_system": 1, "sort_order": 61,
        },

        # ── 系统管理类 (2) ──
        {
            "name": "load_skill", "display_name": "加载技能",
            "category": "system", "tool_type": "builtin",
            "handler_module": "app.mcp.builtin_tools.system_tools._load_skill",
            "description": "加载指定技能的完整执行指令。当系统提示中的「可用技能」列表里存在你需要的技能时，调用此工具获取该技能的详细 prompt 模板或 function 映射。不要猜测技能内容，始终通过此工具按需加载。",
            "input_schema": _json.dumps({
                "type": "object",
                "properties": {
                    "skill_name": {"type": "string", "description": "要加载的技能名称（必须与可用技能列表中的名称完全一致）"},
                },
                "required": ["skill_name"],
            }, ensure_ascii=False),
            "is_enabled": 1, "is_system": 1, "sort_order": 70,
        },
        {
            "name": "get_system_stats", "display_name": "系统统计",
            "category": "system", "tool_type": "builtin",
            "handler_module": "app.mcp.builtin_tools.system_tools._get_system_stats",
            "description": "获取系统整体统计概览，包括用户数、数据仓库记录数、数字员工数、AI模型数、瞭望源数和对话数。当用户询问「系统概况」「系统有多少数据」「整体统计」时使用此工具。",
            "input_schema": _json.dumps({"type": "object", "properties": {}}, ensure_ascii=False),
            "is_enabled": 1, "is_system": 1, "sort_order": 71,
        },
    ]

    for t in tools:
        try:
            conn.execute(
                "INSERT OR IGNORE INTO mcp_tools "
                "(name, display_name, description, category, tool_type, handler_module, "
                "input_schema, output_schema, is_enabled, is_system, sort_order, config) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, '{}', ?, ?, ?, '{}')",
                (t["name"], t["display_name"], t["description"], t["category"],
                 t["tool_type"], t["handler_module"], t["input_schema"],
                 t["is_enabled"], t["is_system"], t["sort_order"]),
            )
        except Exception as e:
            logger.warning(f"种子工具插入失败: {t['name']} — {e}")
    logger.info(f"已插入 {len(tools)} 个 MCP 工具种子数据")



def _check_crawl4ai_migrated(conn) -> bool:
    """v0.11: 检查是否所有旧 crawl4ai_enabled=1 员工已迁移到 mcp_tool_ids。

    如果 mcp_tools 表不存在或 mcp_tool_ids 列不存在，返回 True（无需迁移）。
    如果所有 crawl4ai_enabled=1 的员工 mcp_tool_ids 都包含了爬虫工具，返回 True。
    """
    if not _table_exists(conn, "mcp_tools"):
        return True
    if not _column_exists(conn, "digital_employees", "mcp_tool_ids"):
        return True
    rows = conn.execute(
        "SELECT id, name, mcp_tool_ids FROM digital_employees WHERE crawl4ai_enabled = 1 AND employee_type = 'llm'"
    ).fetchall()
    if not rows:
        return True  # 没有需要迁移的员工
    import json as _json
    # 获取爬虫工具ID
    tool_rows = conn.execute(
        "SELECT id FROM mcp_tools WHERE name IN ('collect_with_crawl4ai', 'batch_deep_collect')"
    ).fetchall()
    tool_ids = {r["id"] for r in tool_rows}
    if not tool_ids:
        return True  # 工具不存在
    for row in rows:
        try:
            existing = set(_json.loads(row["mcp_tool_ids"] or "[]"))
        except (_json.JSONDecodeError, TypeError):
            existing = set()
        if not tool_ids.issubset(existing):
            return False  # 至少一个员工未包含所有爬虫工具
    return True


def _migrate_crawl4ai_to_mcp_tool_ids(conn):
    """v0.11: 将旧 crawl4ai_enabled=1 员工的爬虫权限迁移到 mcp_tool_ids。

    找出所有 crawl4ai_enabled=1 的 LLM 型员工，
    将 collect_with_crawl4ai 和 batch_deep_collect 的 ID 合并到 mcp_tool_ids 中（去重）。
    """
    import json as _json

    tool_rows = conn.execute(
        "SELECT id, name FROM mcp_tools WHERE name IN ('collect_with_crawl4ai', 'batch_deep_collect')"
    ).fetchall()
    tool_id_map = {r["name"]: r["id"] for r in tool_rows}
    if not tool_id_map:
        logger.warning("爬虫工具不存在，跳过 crawl4ai 迁移")
        return

    employees = conn.execute(
        "SELECT id, name, mcp_tool_ids FROM digital_employees "
        "WHERE crawl4ai_enabled = 1 AND employee_type = 'llm'"
    ).fetchall()

    if not employees:
        logger.info("没有需要迁移 crawl4ai 权限的员工")
        return

    migrated = 0
    for emp in employees:
        try:
            existing = set(_json.loads(emp["mcp_tool_ids"] or "[]"))
        except (_json.JSONDecodeError, TypeError):
            existing = set()
        new_ids = existing | set(tool_id_map.values())
        if new_ids != existing:
            conn.execute(
                "UPDATE digital_employees SET mcp_tool_ids = ? WHERE id = ?",
                (_json.dumps(sorted(new_ids), ensure_ascii=False), emp["id"]),
            )
            logger.info(f"  迁移: {emp['name']} (ID={emp['id']}) crawl4ai → mcp_tool_ids "
                        f"(新增 {len(new_ids) - len(existing)} 个工具)")
            migrated += 1

    logger.info(f"crawl4ai 权限迁移完成: {migrated} 个员工已更新")


def _check_legacy_tags_migrated(conn) -> bool:
    """检查员工的 skills 字段是否仍有旧格式字符串标签。"""
    import json as _json
    if not _table_exists(conn, "digital_employees"):
        return True  # 表不存在，跳过
    rows = conn.execute(
        "SELECT skills FROM digital_employees WHERE skills IS NOT NULL AND skills != '[]'"
    ).fetchall()
    for r in rows:
        try:
            arr = _json.loads(r["skills"])
        except (_json.JSONDecodeError, TypeError):
            continue
        if arr and isinstance(arr[0], str):
            return False  # 仍有旧格式字符串标签，需要迁移
    return True  # 所有 skills 都已是 ID 数组或空，无需迁移


def _migrate_legacy_tags_to_skills(conn):
    """v0.10: 将员工旧格式 skills 字符串标签迁移为 Skill ID 数组。

    流程：
    1. 读取所有员工旧格式 skills JSON 字符串数组
    2. 对每个旧 TAG 字符串，在 skills 表中查找或创建同名 Skill
    3. 更新员工的 skills 字段为技能 ID 的 JSON 数组
    4. 为每个员工配置合理的 mcp_tool_ids
    """
    import json as _json

    # 旧 TAG → 新 Skill 映射（参考计划 8.1 节）
    TAG_SKILL_MAP = {
        # 产业专员
        "产业分析": "产业分析",
        "政策解读": "政策解读",
        "竞品分析": "竞品分析",
        "趋势预判": "趋势预判",
        # 天机助手
        "信息检索": "数据搜索",
        "数据分析": "数据统计",
        "文案撰写": "文案撰写",
        "代码辅助": "代码辅助",
        # 采集专员
        "数据搜索": "数据搜索",
        "深度采集": "深度采集",
        "内容提取": "深度采集",
        "数据整理": "数据统计",
        # 文案编写
        "报告撰写": "文案撰写",
        "方案策划": "文案撰写",
        "公文起草": "文案撰写",
        "宣传文案": "文案撰写",
        "演讲稿": "文案撰写",
        # 新闻聚合
        "新闻检索": "新闻摘要",
        "资讯聚合": "新闻摘要",
        "热点追踪": "新闻摘要",
        "每日简报": "新闻摘要",
        # 科普助手
        "百科问答": "百科问答",
        "知识科普": "百科问答",
        "概念解释": "百科问答",
        "学术参考": "百科问答",
        # 随机音乐
        "随机音乐": "随机音乐",
        "歌曲推荐": "随机音乐",
        "音乐点播": "随机音乐",
    }

    # 员工角色 → 推荐 MCP 工具名称映射（v0.10: 使用名称而非硬编码 ID，避免 ID 漂移）
    EMPLOYEE_MCP_TOOL_NAMES = {
        "产业专员": ["search_warehouse", "get_recent_warehouse_data", "get_warehouse_stats",
                    "search_warehouse_fulltext", "collect_web_data", "list_watch_sources"],
        "天机助手": ["search_warehouse", "get_recent_warehouse_data", "get_warehouse_stats",
                    "search_warehouse_fulltext", "collect_web_data", "list_digital_employees",
                    "list_ai_models", "list_conversations", "load_skill"],
        "采集专员": ["search_warehouse", "get_recent_warehouse_data", "search_warehouse_fulltext",
                    "collect_web_data", "deep_collect_url", "list_watch_sources",
                    "collect_with_crawl4ai", "batch_deep_collect"],
        "文案编写": ["search_warehouse", "get_recent_warehouse_data", "list_conversations", "load_skill"],
        "新闻聚合": ["search_warehouse", "get_recent_warehouse_data", "get_warehouse_stats",
                    "search_warehouse_fulltext", "collect_web_data", "list_conversations"],
        "科普助手": ["search_warehouse", "get_recent_warehouse_data", "search_warehouse_fulltext", "load_skill"],
        "随机音乐": ["get_random_music"],
    }

    # 1. 确保需要的 Skill 记录存在
    unique_skill_names = set(TAG_SKILL_MAP.values())
    for sn in unique_skill_names:
        existing = conn.execute(
            "SELECT id FROM skills WHERE name = ?", (sn,)
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO skills (name, description, prompt_template) VALUES (?, ?, ?)",
                (sn, f"自动迁移自旧标签「{sn}」",
                 f"你正在执行「{sn}」任务。请根据用户需求灵活完成任务，必要时使用相应 MCP 工具。"),
            )
            logger.info(f"  创建技能: {sn}")

    # 2. 构建技能名称 → ID 映射
    skill_name_to_id = {}
    all_skills = conn.execute("SELECT id, name FROM skills").fetchall()
    for s in all_skills:
        skill_name_to_id[s["name"]] = s["id"]

    # 3. 迁移每个员工的 skills 字段
    employees = conn.execute(
        "SELECT id, name, skills FROM digital_employees WHERE skills IS NOT NULL AND skills != '[]'"
    ).fetchall()

    migrated_count = 0
    for emp in employees:
        try:
            old_skills = _json.loads(emp["skills"])
        except (_json.JSONDecodeError, TypeError):
            continue

        if not old_skills or not isinstance(old_skills[0], str):
            continue  # 已经是 ID 格式或空

        # 转换旧 TAG → Skill ID
        new_skill_ids = []
        seen_ids = set()
        for tag in old_skills:
            skill_name = TAG_SKILL_MAP.get(tag, tag)
            skill_id = skill_name_to_id.get(skill_name)
            if skill_id and skill_id not in seen_ids:
                new_skill_ids.append(skill_id)
                seen_ids.add(skill_id)

        # 更新 skills 字段
        conn.execute(
            "UPDATE digital_employees SET skills = ? WHERE id = ?",
            (_json.dumps(new_skill_ids, ensure_ascii=False), emp["id"]),
        )

        # 4. 配置 mcp_tool_ids（基于名称解析，避免 ID 漂移）
        emp_name = emp["name"]
        if emp_name in EMPLOYEE_MCP_TOOL_NAMES:
            tool_names = EMPLOYEE_MCP_TOOL_NAMES[emp_name]
            # 按名称查找工具 ID
            valid_ids = []
            for tname in tool_names:
                tool_row = conn.execute(
                    "SELECT id FROM mcp_tools WHERE name = ? AND is_enabled = 1", (tname,)
                ).fetchone()
                if tool_row:
                    valid_ids.append(tool_row["id"])
            if valid_ids:
                conn.execute(
                    "UPDATE digital_employees SET mcp_tool_ids = ? WHERE id = ?",
                    (_json.dumps(valid_ids, ensure_ascii=False), emp["id"]),
                )

        migrated_count += 1

    logger.info(f"旧 TAG 迁移完成: {migrated_count} 个员工的 skills 已转换为 Skill ID 格式")


def _crawl4ai_tool_ids(conn) -> list[int]:
    rows = conn.execute(
        "SELECT id FROM mcp_tools WHERE name IN (?, ?)",
        ("collect_with_crawl4ai", "batch_deep_collect"),
    ).fetchall()
    return [row["id"] for row in rows]


def _check_mcp_catalog_complete(conn) -> bool:
    if not _table_exists(conn, "mcp_tools"):
        return False
    from app.mcp.catalog import canonical_tool_names
    rows = conn.execute("SELECT name FROM mcp_tools").fetchall()
    return canonical_tool_names().issubset({row["name"] for row in rows})


def _check_crawl4ai_permissions_migrated(conn) -> bool:
    if not _column_exists(conn, "digital_employees", "mcp_tool_ids"):
        return False
    tool_ids = set(_crawl4ai_tool_ids(conn))
    if not tool_ids:
        return False
    rows = conn.execute(
        "SELECT mcp_tool_ids FROM digital_employees WHERE crawl4ai_enabled = 1"
    ).fetchall()
    for row in rows:
        try:
            assigned = set(json.loads(row["mcp_tool_ids"] or "[]"))
        except (json.JSONDecodeError, TypeError):
            return False
        if not tool_ids.issubset(assigned):
            return False
    return True


def _migrate_crawl4ai_permissions(conn):
    """Preserve deprecated Crawl4ai capability as explicit MCP grants."""
    tool_ids = _crawl4ai_tool_ids(conn)
    if not tool_ids:
        raise RuntimeError("Crawl4ai MCP 工具尚未初始化")
    rows = conn.execute(
        "SELECT id, mcp_tool_ids FROM digital_employees WHERE crawl4ai_enabled = 1"
    ).fetchall()
    for row in rows:
        try:
            assigned = list(json.loads(row["mcp_tool_ids"] or "[]"))
        except (json.JSONDecodeError, TypeError):
            assigned = []
        for tool_id in tool_ids:
            if tool_id not in assigned:
                assigned.append(tool_id)
        conn.execute(
            "UPDATE digital_employees SET mcp_tool_ids = ? WHERE id = ?",
            (json.dumps(assigned, ensure_ascii=False), row["id"]),
        )


def show_status():
    """显示当前数据库的迁移状态。"""
    if not os.path.exists(DB_PATH):
        print("❌ 数据库文件不存在，无需迁移")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    print(f"📊 数据库: {DB_PATH}")
    print(f"📏 大小: {os.path.getsize(DB_PATH) / 1024:.1f} KB")
    print()
    print("表状态:")
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    for t in tables:
        count = conn.execute(f"SELECT COUNT(*) as cnt FROM {t['name']}").fetchone()["cnt"]
        print(f"  📋 {t['name']}: {count} 行")
    conn.close()


if __name__ == "__main__":
    if "--status" in sys.argv:
        show_status()
    else:
        run_migrations()
