import sqlite3

from app.config.settings import settings
import app.models.db as db_module


def test_init_db_migrates_existing_conversation_messages_review_columns(tmp_path):
    """旧库已有 conversation_messages 表时，也应补齐消息审核列后再建索引。"""
    old_setting = settings.DB_PATH
    old_module = db_module.DB_PATH
    db_path = tmp_path / "legacy.db"

    con = sqlite3.connect(db_path)
    con.execute("""
        CREATE TABLE conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT DEFAULT '新对话',
            username TEXT DEFAULT '',
            model_id INTEGER DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    con.execute("""
        CREATE TABLE conversation_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT DEFAULT '',
            token_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    con.commit()
    con.close()

    try:
        settings.DB_PATH = str(db_path)
        db_module.DB_PATH = str(db_path)
        db_module.init_db()

        con = sqlite3.connect(db_path)
        cols = {row[1] for row in con.execute("PRAGMA table_info(conversation_messages)").fetchall()}
        indexes = {row[1] for row in con.execute("PRAGMA index_list(conversation_messages)").fetchall()}
        con.close()

        assert "is_sensitive" in cols
        assert "review_status" in cols
        assert "idx_conv_msgs_sensitive" in indexes
        assert "idx_conv_msgs_review" in indexes
    finally:
        settings.DB_PATH = old_setting
        db_module.DB_PATH = old_module
