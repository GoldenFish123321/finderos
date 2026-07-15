"""
watch_result.py - watch_results table repository

Data warehouse: stores watch collection execution results.
"""
import json
from app.models.db import get_db


class WatchResultRepository:
    """Collection result data access class."""

    @staticmethod
    def get_all(page: int = 1, page_size: int = 12, keyword: str = "",
                source_id: int = None) -> tuple:
        """Paginated query of collection results. Returns (rows, total)."""
        with get_db() as conn:
            conditions = []
            params = []
            if keyword:
                conditions.append("wr.keyword LIKE ?")
                params.append(f"%{keyword}%")
            if source_id:
                conditions.append("wr.source_id = ?")
                params.append(source_id)
            where = "WHERE " + " AND ".join(conditions) if conditions else ""
            total = conn.execute(
                f"SELECT COUNT(*) as cnt FROM watch_results wr {where}", params
            ).fetchone()["cnt"]
            rows = conn.execute(
                f"SELECT wr.*, ws.name as source_name "
                f"FROM watch_results wr LEFT JOIN watch_sources ws ON wr.source_id = ws.id "
                f"{where} ORDER BY wr.id DESC LIMIT ? OFFSET ?",
                (*params, page_size, (page - 1) * page_size),
            ).fetchall()
        return rows, total

    @staticmethod
    def create(source_id: int, keyword: str, request_url: str,
               response_status: int = 0, response_size: int = 0,
               result_data: str = "") -> int:
        """Create a collection result record. Returns new ID."""
        with get_db() as conn:
            cur = conn.execute(
                "INSERT INTO watch_results (source_id, keyword, request_url, "
                "response_status, response_size, result_data) VALUES (?, ?, ?, ?, ?, ?)",
                (source_id, keyword, request_url, response_status, response_size, result_data),
            )
            conn.commit()
            return cur.lastrowid

    @staticmethod
    def get_by_id(result_id: int):
        """Get collection result by ID."""
        with get_db() as conn:
            return conn.execute(
                "SELECT wr.*, ws.name as source_name "
                "FROM watch_results wr LEFT JOIN watch_sources ws ON wr.source_id = ws.id "
                "WHERE wr.id = ?", (result_id,)
            ).fetchone()

    @staticmethod
    def delete(result_id: int) -> bool:
        """Delete a collection result."""
        with get_db() as conn:
            cursor = conn.execute("DELETE FROM watch_results WHERE id = ?", (result_id,))
            return cursor.rowcount > 0

    @staticmethod
    def get_count() -> int:
        """Get total result count."""
        with get_db() as conn:
            return conn.execute("SELECT COUNT(*) as cnt FROM watch_results").fetchone()["cnt"]

    @staticmethod
    def mark_saved(result_id: int) -> bool:
        """Mark a result as saved to warehouse."""
        with get_db() as conn:
            cursor = conn.execute(
                "UPDATE watch_results SET result_data = 'SAVED:' || COALESCE(result_data, '') WHERE id = ?",
                (result_id,),
            )
            return cursor.rowcount > 0

    @staticmethod
    def get_saved(page: int = 1, page_size: int = 20, keyword: str = "") -> tuple:
        """Get results saved to warehouse."""
        with get_db() as conn:
            conditions = ["wr.result_data LIKE 'SAVED:%'"]
            params = []
            if keyword:
                conditions.append("wr.keyword LIKE ?")
                params.append(f"%{keyword}%")
            where = "WHERE " + " AND ".join(conditions)
            total = conn.execute(
                f"SELECT COUNT(*) as cnt FROM watch_results wr {where}", params
            ).fetchone()["cnt"]
            rows = conn.execute(
                f"SELECT wr.*, ws.name as source_name "
                f"FROM watch_results wr LEFT JOIN watch_sources ws ON wr.source_id = ws.id "
                f"{where} ORDER BY wr.id DESC LIMIT ? OFFSET ?",
                (*params, page_size, (page - 1) * page_size),
            ).fetchall()
        return rows, total

    @staticmethod
    def get_stats() -> dict:
        """Get warehouse statistics."""
        with get_db() as conn:
            total = conn.execute("SELECT COUNT(*) as cnt FROM watch_results").fetchone()["cnt"]
            saved = conn.execute(
                "SELECT COUNT(*) as cnt FROM watch_results WHERE result_data LIKE 'SAVED:%'"
            ).fetchone()["cnt"]
            success = conn.execute(
                "SELECT COUNT(*) as cnt FROM watch_results WHERE response_status = 200"
            ).fetchone()["cnt"]
            total_size = conn.execute(
                "SELECT COALESCE(SUM(response_size), 0) as total FROM watch_results"
            ).fetchone()["total"]
            source_count = conn.execute(
                "SELECT COUNT(DISTINCT source_id) as cnt FROM watch_results WHERE source_id IS NOT NULL"
            ).fetchone()["cnt"]
            return {
                "total": total, "saved": saved, "success": success,
                "total_size": total_size, "source_count": source_count,
            }

    @staticmethod
    def check_url_exists(request_url: str) -> bool:
        """Check if a URL already exists in watch_results (URL dedup)."""
        if not request_url:
            return False
        with get_db() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM watch_results WHERE request_url = ?",
                (request_url,)
            ).fetchone()
            return row["cnt"] > 0

    @staticmethod
    def create_if_not_exists(source_id: int, keyword: str, request_url: str,
                              response_status: int = 0, response_size: int = 0,
                              result_data: str = "") -> tuple:
        """
        Create a collection result if URL doesn't already exist.
        Uses INSERT OR IGNORE with UNIQUE index for atomic dedup.
        Returns (new_id, is_new) — is_new is True if created, False if duplicate skipped.
        """
        with get_db() as conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO watch_results (source_id, keyword, request_url, "
                "response_status, response_size, result_data) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (source_id, keyword, request_url,
                 response_status, response_size, result_data),
            )
            if cur.rowcount > 0:
                conn.commit()
                return cur.lastrowid, True
            return 0, False

    @staticmethod
    def mark_saved_batch(result_ids: list) -> tuple:
        """
        Batch mark results as saved to warehouse, with URL dedup.
        Returns (saved_count, skipped_count).
        """
        saved = 0
        skipped = 0
        with get_db() as conn:
            for rid in result_ids:
                row = conn.execute(
                    "SELECT request_url FROM watch_results WHERE id = ?", (rid,)
                ).fetchone()
                if not row:
                    skipped += 1
                    continue
                # Check if already saved
                current = conn.execute(
                    "SELECT result_data FROM watch_results WHERE id = ?", (rid,)
                ).fetchone()
                if current and (current["result_data"] or "").startswith("SAVED:"):
                    skipped += 1
                    continue
                # Mark as saved
                conn.execute(
                    "UPDATE watch_results SET result_data = 'SAVED:' || COALESCE(result_data, '') WHERE id = ?",
                    (rid,),
                )
                saved += 1
            conn.commit()
        return saved, skipped
