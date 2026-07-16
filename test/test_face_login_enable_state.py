import sqlite3

from app.config.settings import settings
import app.models.db as db_module
from app.models.user import UserRepository


def test_face_login_enabled_migration_and_repository(tmp_path):
    """人脸登录必须有独立的后端持久化开关，默认关闭，可独立启停。"""
    old_setting = settings.DB_PATH
    old_module = db_module.DB_PATH
    db_path = tmp_path / "legacy-face.db"

    con = sqlite3.connect(db_path)
    con.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            role_id INTEGER DEFAULT NULL,
            is_enabled INTEGER DEFAULT 1,
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
        cols = {row[1] for row in con.execute("PRAGMA table_info(users)").fetchall()}
        con.close()
        assert "face_login_enabled" in cols

        assert UserRepository.create_user("face_user", "password123") is True
        assert UserRepository.is_face_login_enabled("face_user") is False
        assert UserRepository.set_face_login_enabled("face_user", True) is True
        assert UserRepository.is_face_login_enabled("face_user") is True
        assert UserRepository.set_face_login_enabled("face_user", False) is True
        assert UserRepository.is_face_login_enabled("face_user") is False
    finally:
        settings.DB_PATH = old_setting
        db_module.DB_PATH = old_module
