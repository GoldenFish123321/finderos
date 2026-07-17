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
  v1.10 — 添加 watch_sources.parser 列并迁移已有源解析器
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


def _add_watch_source_parser(conn):
    conn.execute("ALTER TABLE watch_sources ADD COLUMN parser TEXT DEFAULT 'generic'")
    conn.execute(
        "UPDATE watch_sources SET parser = CASE "
        "WHEN lower(url_template) LIKE '%baidu.com%' THEN 'baidu_news' "
        "WHEN lower(url_template) LIKE '%sogou.com%' THEN 'sogou_news' "
        "WHEN lower(url_template) LIKE '%bing.com%' THEN 'bing_rss' "
        "ELSE 'generic' END"
    )


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
        {
            "name": "add_watch_sources_parser",
            "run": _add_watch_source_parser,
            "check": lambda c: _column_exists(c, "watch_sources", "parser"),
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
        # v2.0 统一接口驱动架构 — api_interfaces 新增字段
        {
            "name": "add_api_interfaces_interface_type",
            "sql": "ALTER TABLE api_interfaces ADD COLUMN interface_type TEXT DEFAULT 'external'",
            "check": lambda c: _column_exists(c, "api_interfaces", "interface_type"),
        },
        {
            "name": "add_api_interfaces_is_system",
            "sql": "ALTER TABLE api_interfaces ADD COLUMN is_system INTEGER DEFAULT 0",
            "check": lambda c: _column_exists(c, "api_interfaces", "is_system"),
        },
        {
            "name": "add_api_interfaces_local_handler",
            "sql": "ALTER TABLE api_interfaces ADD COLUMN local_handler TEXT DEFAULT ''",
            "check": lambda c: _column_exists(c, "api_interfaces", "local_handler"),
        },
        {
            "name": "add_api_interfaces_response_content_type",
            "sql": "ALTER TABLE api_interfaces ADD COLUMN response_content_type TEXT DEFAULT 'json'",
            "check": lambda c: _column_exists(c, "api_interfaces", "response_content_type"),
        },
        # v2.0 统一接口驱动架构 — mcp_tools 新增字段
        {
            "name": "add_mcp_tools_data_sources",
            "sql": "ALTER TABLE mcp_tools ADD COLUMN data_sources TEXT DEFAULT '[]'",
            "check": lambda c: _column_exists(c, "mcp_tools", "data_sources"),
        },
        {
            "name": "add_mcp_tools_transform_script",
            "sql": "ALTER TABLE mcp_tools ADD COLUMN transform_script TEXT DEFAULT ''",
            "check": lambda c: _column_exists(c, "mcp_tools", "transform_script"),
        },
        {
            "name": "add_mcp_tools_script_enabled",
            "sql": "ALTER TABLE mcp_tools ADD COLUMN script_enabled INTEGER DEFAULT 0",
            "check": lambda c: _column_exists(c, "mcp_tools", "script_enabled"),
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
