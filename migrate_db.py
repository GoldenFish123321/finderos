#!/usr/bin/env python3
"""
migrate_db.py — 数据库迁移脚本

向后兼容地为现有数据库添加新列/新表，不破坏已有数据。
在项目根目录运行：python migrate_db.py

迁移历史:
  v0.2.5  — 添加 ai_models.total_tokens (Token 累加统计)
  v0.2.5  — 添加 audit_logs 表 (操作审计日志)
  v0.2.5  — 添加安全相关索引
  v0.2.13 — 添加 data_warehouse 独立表 + URL 去重索引
  v0.3.0  — 添加 conversations / conversation_messages 表
  v0.3.0  — 添加 digital_employees 表
  v0.3.0  — 添加 data_warehouse_fts 虚拟表 + 同步触发器
  v0.4.0  — 添加 watch_sources.schedule_interval 列
  v0.5.0  — 添加 skills 技能库表

Usage:
  python migrate_db.py              # 执行待处理迁移
  python migrate_db.py --status     # 查看迁移状态
"""

import logging
import os
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
        # v0.2.5: ai_models 新增 total_tokens 列
        {
            "name": "add_ai_models_total_tokens",
            "sql": "ALTER TABLE ai_models ADD COLUMN total_tokens INTEGER DEFAULT 0",
            "check": lambda c: _column_exists(c, "ai_models", "total_tokens"),
        },
        # v0.2.5: 审计日志表
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
        # v0.2.5: 审计日志索引
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
        # v0.3.0: 对话管理表
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
        # v0.3.0: 数字化员工表
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
        # v0.3.0: FTS5 全文检索虚拟表 + 同步触发器
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
        # v0.4.0: 瞭望源定时采集间隔
        {
            "name": "add_watch_sources_schedule_interval",
            "sql": "ALTER TABLE watch_sources ADD COLUMN schedule_interval INTEGER DEFAULT 0",
            "check": lambda c: _column_exists(c, "watch_sources", "schedule_interval"),
        },
        # v0.5.0: 技能库表
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
    ]

    applied = 0
    skipped = 0

    for m in migrations:
        try:
            if m["check"](conn):
                logger.info(f"⏭️  跳过（已存在）: {m['name']}")
                skipped += 1
                continue
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
