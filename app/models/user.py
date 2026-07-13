"""
user.py - Users table repository (Repository pattern)
"""
import hashlib
import secrets
import sqlite3

from app.config.settings import settings
from app.models.db import get_db


def _hash_password(password: str, salt: bytes) -> str:
    """Hash password with PBKDF2-HMAC-SHA256."""
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, settings.PBKDF2_ITERATIONS)
    return dk.hex()


class UserRepository:
    """User data access class."""

    @staticmethod
    def create_user(username: str, password: str, role_id: int = None) -> bool:
        """Create a new user. Returns True on success."""
        salt = secrets.token_bytes(16)
        password_hash = _hash_password(password, salt)
        try:
            with get_db() as conn:
                conn.execute(
                    "INSERT INTO users (username, password_hash, salt, role_id) VALUES (?, ?, ?, ?)",
                    (username.strip(), password_hash, salt.hex(), role_id),
                )
                conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    @staticmethod
    def verify_user(username: str, password: str) -> bool:
        """Verify username and password."""
        with get_db() as conn:
            row = conn.execute(
                "SELECT password_hash, salt, is_enabled FROM users WHERE username = ?",
                (username,),
            ).fetchone()
        if row is None:
            return False
        if row["is_enabled"] == 0:
            return False
        expected = _hash_password(password, bytes.fromhex(row["salt"]))
        return expected == row["password_hash"]

    @staticmethod
    def get_user_by_username(username: str):
        """Get user by username."""
        with get_db() as conn:
            return conn.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            ).fetchone()

    @staticmethod
    def get_user_by_id(user_id: int):
        """Get user by ID."""
        with get_db() as conn:
            return conn.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            ).fetchone()

    @staticmethod
    def get_user_count() -> int:
        """Get total user count."""
        with get_db() as conn:
            return conn.execute("SELECT COUNT(*) as cnt FROM users").fetchone()["cnt"]

    @staticmethod
    def get_all(page: int = 1, page_size: int = 20, keyword: str = "") -> tuple:
        """Paginated query of users. Returns (rows, total)."""
        with get_db() as conn:
            conditions = []
            params = []
            if keyword:
                conditions.append("username LIKE ?")
                params.append(f"%{keyword}%")
            where = "WHERE " + " AND ".join(conditions) if conditions else ""
            total = conn.execute(
                f"SELECT COUNT(*) as cnt FROM users {where}", params
            ).fetchone()["cnt"]
            rows = conn.execute(
                f"SELECT u.*, r.name as role_name FROM users u "
                f"LEFT JOIN roles r ON u.role_id = r.id "
                f"{where} ORDER BY u.id DESC LIMIT ? OFFSET ?",
                (*params, page_size, (page - 1) * page_size),
            ).fetchall()
        return rows, total

    @staticmethod
    def get_user_role(username: str):
        """Get the role assigned to a user."""
        with get_db() as conn:
            return conn.execute(
                "SELECT r.* FROM users u LEFT JOIN roles r ON u.role_id = r.id WHERE u.username = ?",
                (username,),
            ).fetchone()

    @staticmethod
    def get_user_functions(username: str) -> list:
        """Get function IDs accessible to a user (via their role)."""
        with get_db() as conn:
            rows = conn.execute(
                "SELECT rf.function_id FROM users u "
                "JOIN role_functions rf ON u.role_id = rf.role_id "
                "WHERE u.username = ?",
                (username,),
            ).fetchall()
        return [r["function_id"] for r in rows]

    @staticmethod
    def update_user(user_id: int, username: str, password: str = "", role_id: int = None) -> bool:
        """Update user info. If password is empty, keep existing."""
        try:
            with get_db() as conn:
                if password:
                    salt = secrets.token_bytes(16)
                    password_hash = _hash_password(password, salt)
                    conn.execute(
                        "UPDATE users SET username=?, password_hash=?, salt=?, role_id=? WHERE id=?",
                        (username.strip(), password_hash, salt.hex(), role_id, user_id),
                    )
                else:
                    conn.execute(
                        "UPDATE users SET username=?, role_id=? WHERE id=?",
                        (username.strip(), role_id, user_id),
                    )
                conn.commit()
            return conn.total_changes > 0
        except sqlite3.IntegrityError:
            return False

    @staticmethod
    def delete_user(user_id: int) -> bool:
        """Delete a user. Cannot delete admin."""
        with get_db() as conn:
            user = conn.execute(
                "SELECT username FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            if not user or user["username"] == "admin":
                return False
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            conn.commit()
            return conn.total_changes > 0

    @staticmethod
    def toggle_enabled(user_id: int) -> int:
        """Toggle user enabled/disabled. Returns new status (0/1), -1 if not found, -2 if admin."""
        with get_db() as conn:
            row = conn.execute(
                "SELECT username, is_enabled FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            if not row:
                return -1
            if row["username"] == "admin":
                return -2
            new_status = 0 if row["is_enabled"] == 1 else 1
            conn.execute(
                "UPDATE users SET is_enabled = ? WHERE id = ?", (new_status, user_id)
            )
            conn.commit()
            return new_status

    @staticmethod
    def batch_delete(ids: list[int]) -> int:
        """批量删除用户（排除 admin）。返回成功删除数。"""
        count = 0
        with get_db() as conn:
            for uid in ids:
                user = conn.execute(
                    "SELECT username FROM users WHERE id = ?", (uid,)
                ).fetchone()
                if user and user["username"] != "admin":
                    conn.execute("DELETE FROM users WHERE id = ?", (uid,))
                    count += 1
            conn.commit()
        return count

    @staticmethod
    def batch_toggle(ids: list[int], enable: bool) -> int:
        """批量启用/禁用用户（排除 admin）。返回成功操作数。"""
        count = 0
        new_status = 1 if enable else 0
        with get_db() as conn:
            for uid in ids:
                user = conn.execute(
                    "SELECT username FROM users WHERE id = ?", (uid,)
                ).fetchone()
                if user and user["username"] != "admin":
                    conn.execute(
                        "UPDATE users SET is_enabled = ? WHERE id = ?",
                        (new_status, uid),
                    )
                    count += 1
            conn.commit()
        return count
