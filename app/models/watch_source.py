"""
watch_source.py - watch_sources table repository (Repository pattern)
"""
import json
import sqlite3
from app.models.db import get_db


class WatchSourceRepository:
    """Watch source data access class."""

    @staticmethod
    def get_all(page: int = 1, page_size: int = 20, keyword: str = "") -> tuple:
        """Paginated query of watch sources. Returns (rows, total)."""
        with get_db() as conn:
            conditions = []
            params = []
            if keyword:
                conditions.append("name LIKE ?")
                params.append(f"%{keyword}%")
            where = "WHERE " + " AND ".join(conditions) if conditions else ""
            total = conn.execute(
                f"SELECT COUNT(*) as cnt FROM watch_sources {where}", params
            ).fetchone()["cnt"]
            rows = conn.execute(
                f"SELECT * FROM watch_sources {where} ORDER BY sort_order ASC, id ASC "
                f"LIMIT ? OFFSET ?",
                (*params, page_size, (page - 1) * page_size),
            ).fetchall()
        return rows, total

    @staticmethod
    def get_enabled() -> list:
        """Get all enabled watch sources."""
        with get_db() as conn:
            return conn.execute(
                "SELECT * FROM watch_sources WHERE is_enabled = 1 ORDER BY sort_order ASC"
            ).fetchall()

    @staticmethod
    def get_by_id(source_id: int):
        """Get watch source by ID."""
        with get_db() as conn:
            return conn.execute(
                "SELECT * FROM watch_sources WHERE id = ?", (source_id,)
            ).fetchone()

    @staticmethod
    def create(name: str, description: str, url_template: str,
               request_headers: str = "{}", sort_order: int = 0) -> bool:
        """Create a watch source."""
        try:
            json.loads(request_headers)  # Validate JSON format
        except json.JSONDecodeError:
            return False
        try:
            with get_db() as conn:
                conn.execute(
                    "INSERT INTO watch_sources (name, description, url_template, "
                    "request_headers, sort_order) VALUES (?, ?, ?, ?, ?)",
                    (name.strip(), description.strip(), url_template.strip(),
                     request_headers, sort_order),
                )
                conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    @staticmethod
    def update(source_id: int, name: str, description: str, url_template: str,
               request_headers: str = "{}", sort_order: int = 0) -> bool:
        """Update a watch source."""
        try:
            json.loads(request_headers)  # Validate JSON format
        except json.JSONDecodeError:
            return False
        try:
            with get_db() as conn:
                conn.execute(
                    "UPDATE watch_sources SET name=?, description=?, url_template=?, "
                    "request_headers=?, sort_order=? WHERE id=?",
                    (name.strip(), description.strip(), url_template.strip(),
                     request_headers, sort_order, source_id),
                )
                conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    @staticmethod
    def delete(source_id: int) -> bool:
        """Delete a watch source."""
        with get_db() as conn:
            cursor = conn.execute("DELETE FROM watch_sources WHERE id = ?", (source_id,))
            conn.commit()
            return cursor.rowcount > 0

    @staticmethod
    def toggle_enabled(source_id: int) -> int:
        """Toggle enabled/disabled status. Returns new status or -1."""
        with get_db() as conn:
            row = conn.execute(
                "SELECT is_enabled FROM watch_sources WHERE id = ?", (source_id,)
            ).fetchone()
            if not row:
                return -1
            new_status = 0 if row["is_enabled"] == 1 else 1
            conn.execute(
                "UPDATE watch_sources SET is_enabled = ? WHERE id = ?",
                (new_status, source_id),
            )
            conn.commit()
            return new_status

    @staticmethod
    def get_all_enabled() -> list:
        """获取所有启用的瞭望源（含调度配置）。"""
        with get_db() as conn:
            return conn.execute(
                "SELECT * FROM watch_sources WHERE is_enabled = 1 "
                "AND schedule_interval > 0 ORDER BY sort_order ASC"
            ).fetchall()

    @staticmethod
    def get_count() -> int:
        """Get total source count."""
        with get_db() as conn:
            return conn.execute(
                "SELECT COUNT(*) as cnt FROM watch_sources"
            ).fetchone()["cnt"]

    @staticmethod
    def get_headers(source_id: int) -> dict:
        """Get parsed request headers for a watch source."""
        with get_db() as conn:
            row = conn.execute(
                "SELECT request_headers FROM watch_sources WHERE id = ?", (source_id,)
            ).fetchone()
        if not row:
            return {}
        try:
            return json.loads(row["request_headers"])
        except (json.JSONDecodeError, TypeError):
            return {}
