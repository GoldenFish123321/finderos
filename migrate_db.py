#!/usr/bin/env python3
"""
migrate_db.py — 数据库迁移脚本

向后兼容地为现有数据库添加新列/新表，不破坏已有数据。
在项目根目录运行：python migrate_db.py

迁移历史:
  v0.2.5 — 添加 ai_models.total_tokens (Token 累加统计)
  v0.2.5 — 添加 audit_logs 表 (操作审计日志)
  v0.2.5 — 添加安全相关索引

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
