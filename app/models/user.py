"""
user.py �?users 表的仓储对象

采用 Repository 模式：把 SQL + 数据访问集中到一个类里，controller 只调用方法�?实现与数据库表有关的操作：新�?修改/删除/查询等�?
安全规范�?- 密码使用 PBKDF2-SHA256 + 随机盐存储，迭代 600,000 �?- 全部 SQL 使用 ? 参数占位符，防止注入
"""

import hashlib
import secrets
import sqlite3

from app.config.settings import settings
from app.models.db import get_db


def _hash_password(password: str, salt: bytes) -> str:
    """
    将明文密�?+ salt 计算为稳定的哈希�?    使用 PBKDF2-HMAC-SHA256，迭�?600,000 次（OWASP 2023 推荐）�?    """
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, settings.PBKDF2_ITERATIONS)
    return dk.hex()


class UserRepository:
    """
    用户数据访问类（面向 Controller 提供方法）�?    """

    # ========== 基础方法 ==========

    @staticmethod
    def create_user(username: str, password: str, role_id: int = None) -> bool:
        """
        创建新用户�?        返回 True 表示成功，False 表示用户名已存在�?        """
        salt = secrets.token_bytes(16)
        password_hash = _hash_password(password, salt)
        try:
            with get_db() as conn:
                conn.execute(
                    "INSERT INTO users (username, password_hash, salt, role_id) VALUES (?, ?, ?, ?)",
                    (username, password_hash, salt.hex(), role_id),
                )
                conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    @staticmethod
    def verify_user(username: str, password: str) -> bool:
        """
        验证用户名和密码�?        返回 True 表示验证通过，False 表示用户名不存在或密码错误�?        """
        with get_db() as conn:
            row = conn.execute(
                "SELECT password_hash, salt, is_enabled FROM users WHERE username = ?",
                (username,),
            ).fetchone()

        if row is None:
            return False
        if row["is_enabled"] == 0:
            return False

        stored_hash = row["password_hash"]
        salt = bytes.fromhex(row["salt"])
        computed_hash = _hash_password(password, salt)

        return secrets.compare_digest(computed_hash, stored_hash)

    @staticmethod
    def get_user_by_username(username: str):
        """根据用户名查询用户信息�?""
        with get_db() as conn:
            return conn.execute(
                "SELECT id, username, password_hash, salt, role_id, is_enabled, created_at "
                "FROM users WHERE username = ?",
                (username,),
            ).fetchone()

    @staticmethod
    def get_user_by_id(user_id: int):
        """根据 ID 查询用户信息�?""
        with get_db() as conn:
            return conn.execute(
                "SELECT u.id, u.username, u.role_id, u.is_enabled, u.created_at, "
                "r.name as role_name "
                "FROM users u LEFT JOIN roles r ON u.role_id = r.id "
                "WHERE u.id = ?",
                (user_id,),
            ).fetchone()

    @staticmethod
    def get_user_count() -> int:
        """获取用户总数�?""
        with get_db() as conn:
            return conn.execute("SELECT COUNT(*) as cnt FROM users").fetchone()["cnt"]

    # ========== 管理端方�?==========

    @staticmethod
    def get_all(page: int = 1, page_size: int = 20,
                keyword: str = "") -> tuple:
        """
        分页查询用户列表（管理端）�?        返回 (rows, total)�?        """
        with get_db() as conn:
            if keyword:
                where = "WHERE u.username LIKE ?"
                params = (f"%{keyword}%",)
            else:
                where = ""
                params = ()

            total = conn.execute(
                f"SELECT COUNT(*) as cnt FROM users u {where}", params
            ).fetchone()["cnt"]

            rows = conn.execute(
                f"SELECT u.id, u.username, u.role_id, u.is_enabled, u.created_at, "
                f"r.name as role_name "
                f"FROM users u LEFT JOIN roles r ON u.role_id = r.id "
                f"{where} "
                f"ORDER BY u.id ASC LIMIT ? OFFSET ?",
                (*params, page_size, (page - 1) * page_size),
            ).fetchall()
        return rows, total

    @staticmethod
    def update_user(user_id: int, username: str = None,
                    password: str = None, role_id: int = None) -> bool:
        """
        更新用户信息。传�?None 的字段不更新�?        """
        fields = []
        values = []
        if username is not None:
            fields.append("username = ?")
            values.append(username.strip())
        if password is not None:
            salt = secrets.token_bytes(16)
            password_hash = _hash_password(password, salt)
            fields.append("password_hash = ?")
            values.append(password_hash)
            fields.append("salt = ?")
            values.append(salt.hex())
        if role_id is not None:
            fields.append("role_id = ?")
            values.append(role_id)
        if not fields:
            return False

        values.append(user_id)
        try:
            with get_db() as conn:
                conn.execute(
                    f"UPDATE users SET {', '.join(fields)} WHERE id = ?",
                    values,
                )
                conn.commit()
            return conn.total_changes > 0
        except sqlite3.IntegrityError:
            return False

    @staticmethod
    def delete_user(user_id: int) -> bool:
        """删除用户�?""
        with get_db() as conn:
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            conn.commit()
            return conn.total_changes > 0

    @staticmethod
    def toggle_enabled(user_id: int) -> int:
        """
        切换用户的启�?禁用状态�?        返回新状�?(0=禁用, 1=启用)�?1 表示用户不存在�?        """
        with get_db() as conn:
            row = conn.execute(
                "SELECT is_enabled, username FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            if not row:
                return -1
            # admin 不允许禁用自�?            if row["username"] == "admin":
                return -2
            new_status = 0 if row["is_enabled"] == 1 else 1
            conn.execute(
                "UPDATE users SET is_enabled = ? WHERE id = ?", (new_status, user_id)
            )
            conn.commit()
            return new_status

    @staticmethod
    def get_user_role(username: str) -> dict | None:
        """获取用户的角色信息�?""
        with get_db() as conn:
            return conn.execute(
                "SELECT r.id, r.name, r.description, r.is_system "
                "FROM users u LEFT JOIN roles r ON u.role_id = r.id "
                "WHERE u.username = ?",
                (username,),
            ).fetchone()

    @staticmethod
    def get_user_functions(username: str) -> list:
        """获取用户拥有的功能列表（通过角色关联）�?""
        with get_db() as conn:
            rows = conn.execute(
                "SELECT DISTINCT f.id, f.name, f.icon, f.route_path, f.parent_id, f.sort_order "
                "FROM users u "
                "JOIN role_functions rf ON u.role_id = rf.role_id "
                "JOIN functions f ON rf.function_id = f.id "
                "WHERE u.username = ? AND f.is_enabled = 1 "
                "ORDER BY f.parent_id ASC, f.sort_order ASC",
                (username,),
            ).fetchall()
        return rows
