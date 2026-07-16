"""
system_config.py — SystemConfigRepository

Key-value configuration persistence layer.
Provides CRUD for system-wide settings stored in the system_config table.
Follows the existing Repository pattern: all @staticmethod, pure SQL, get_db() context.
"""
import logging
import sqlite3

from app.models.db import get_db

logger = logging.getLogger(__name__)


class SystemConfigRepository:
    """Repository for system_config key-value table."""

    @staticmethod
    def get_all() -> list[dict]:
        """Return all config rows ordered by category, key."""
        with get_db() as conn:
            return conn.execute(
                "SELECT * FROM system_config ORDER BY category, key"
            ).fetchall()

    @staticmethod
    def get_by_key(key: str) -> dict | None:
        """Return a single config row by key, or None."""
        with get_db() as conn:
            return conn.execute(
                "SELECT * FROM system_config WHERE key = ?", (key,)
            ).fetchone()

    @staticmethod
    def get_all_as_dict() -> dict[str, str]:
        """Return all config as {key: value} dict — used by settings.py for bulk loading."""
        with get_db() as conn:
            rows = conn.execute("SELECT key, value FROM system_config").fetchall()
            return {row["key"]: row["value"] for row in rows}

    @staticmethod
    def get_by_category(category: str) -> list[dict]:
        """Return config rows filtered by category."""
        with get_db() as conn:
            return conn.execute(
                "SELECT * FROM system_config WHERE category = ? ORDER BY key", (category,)
            ).fetchall()

    @staticmethod
    def update(key: str, value: str) -> bool:
        """Update a single config key. Returns True on success."""
        try:
            with get_db() as conn:
                cursor = conn.execute(
                    "UPDATE system_config SET value = ?, updated_at = CURRENT_TIMESTAMP WHERE key = ?",
                    (value, key),
                )
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"SystemConfigRepository.update({key}): {e}")
            return False

    @staticmethod
    def bulk_update(updates: dict[str, str]) -> int:
        """Batch update multiple config keys. Returns count of updated rows, -1 on error."""
        count = 0
        try:
            with get_db() as conn:
                for key, value in updates.items():
                    cursor = conn.execute(
                        "UPDATE system_config SET value = ?, updated_at = CURRENT_TIMESTAMP WHERE key = ?",
                        (value, key),
                    )
                    count += cursor.rowcount
                conn.commit()
        except Exception as e:
            logger.error(f"SystemConfigRepository.bulk_update: {e}")
            return -1
        return count

    @staticmethod
    def upsert(key: str, value: str, description: str = "", category: str = "general") -> bool:
        """Insert or update a config key. Returns True on success."""
        try:
            with get_db() as conn:
                conn.execute(
                    "INSERT INTO system_config (key, value, description, category) "
                    "VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
                    "description = excluded.description, category = excluded.category, "
                    "updated_at = CURRENT_TIMESTAMP",
                    (key, value, description, category),
                )
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"SystemConfigRepository.upsert({key}): {e}")
            return False
