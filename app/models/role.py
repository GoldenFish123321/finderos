"""
role.py - Roles table repository (Repository pattern)
"""
import sqlite3
from app.models.db import get_db


class RoleRepository:
    """Role data access class."""

    @staticmethod
    def get_all(page: int = 1, page_size: int = 20) -> tuple:
        """Paginated query of all roles. Returns (rows, total)."""
        with get_db() as conn:
            total = conn.execute("SELECT COUNT(*) as cnt FROM roles").fetchone()["cnt"]
            rows = conn.execute(
                "SELECT * FROM roles ORDER BY id ASC LIMIT ? OFFSET ?",
                (page_size, (page - 1) * page_size),
            ).fetchall()
        return rows, total

    @staticmethod
    def get_by_id(role_id: int):
        """Get role by ID."""
        with get_db() as conn:
            return conn.execute(
                "SELECT * FROM roles WHERE id = ?", (role_id,)
            ).fetchone()

    @staticmethod
    def get_by_name(name: str):
        """Get role by name."""
        with get_db() as conn:
            return conn.execute(
                "SELECT * FROM roles WHERE name = ?", (name,)
            ).fetchone()

    @staticmethod
    def create(name: str, description: str = "") -> bool:
        """Create a new role."""
        try:
            with get_db() as conn:
                conn.execute(
                    "INSERT INTO roles (name, description) VALUES (?, ?)",
                    (name.strip(), description.strip()),
                )
                conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    @staticmethod
    def update(role_id: int, name: str, description: str = "") -> bool:
        """Update a role. System roles (is_system=1) cannot be edited."""
        with get_db() as conn:
            row = conn.execute(
                "SELECT is_system FROM roles WHERE id = ?", (role_id,)
            ).fetchone()
            if not row or row["is_system"] == 1:
                return False
            cursor = conn.execute(
                "UPDATE roles SET name=?, description=? WHERE id=?",
                (name.strip(), description.strip(), role_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    @staticmethod
    def delete(role_id: int) -> bool:
        """Delete a role. System roles cannot be deleted."""
        with get_db() as conn:
            row = conn.execute(
                "SELECT is_system FROM roles WHERE id = ?", (role_id,)
            ).fetchone()
            if not row or row["is_system"] == 1:
                return False
            cursor = conn.execute("DELETE FROM roles WHERE id = ?", (role_id,))
            conn.commit()
            return cursor.rowcount > 0

    @staticmethod
    def get_count() -> int:
        """Get total role count."""
        with get_db() as conn:
            return conn.execute("SELECT COUNT(*) as cnt FROM roles").fetchone()["cnt"]

    @staticmethod
    def get_function_ids(role_id: int) -> list:
        """Get function IDs assigned to a role."""
        with get_db() as conn:
            rows = conn.execute(
                "SELECT function_id FROM role_functions WHERE role_id = ?", (role_id,)
            ).fetchall()
        return [r["function_id"] for r in rows]

    @staticmethod
    def set_functions(role_id: int, function_ids: list) -> bool:
        """Replace all function assignments for a role."""
        with get_db() as conn:
            conn.execute("DELETE FROM role_functions WHERE role_id = ?", (role_id,))
            conn.executemany(
                "INSERT INTO role_functions (role_id, function_id) VALUES (?, ?)",
                [(role_id, fid) for fid in function_ids],
            )
            conn.commit()
        return True
