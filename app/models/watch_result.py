"""
watch_result.py �?watch_results 表的仓储对象

数据仓库：存储瞭望采集的执行结果�?"""
import json
from app.models.db import get_db


class WatchResultRepository:
    """采集结果数据访问�?""

    @staticmethod
    def get_all(page: int = 1, page_size: int = 12, keyword: str = "",
                source_id: int = None) -> tuple:
        """分页查询采集结果，返�?(rows, total)�?""
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
        """创建采集结果记录，返回新 ID�?""
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
        """根据 ID 查询采集结果�?""
        with get_db() as conn:
            return conn.execute(
                "SELECT wr.*, ws.name as source_name "
                "FROM watch_results wr LEFT JOIN watch_sources ws ON wr.source_id = ws.id "
                "WHERE wr.id = ?", (result_id,)
            ).fetchone()

    @staticmethod
    def delete(result_id: int) -> bool:
        """删除采集结果�?""
        with get_db() as conn:
            conn.execute("DELETE FROM watch_results WHERE id = ?", (result_id,))
            conn.commit()
            return True

    @staticmethod
    def get_count() -> int:
        """获取结果总数�?""
        with get_db() as conn:
            return conn.execute("SELECT COUNT(*) as cnt FROM watch_results").fetchone()["cnt"]

    @staticmethod
    def mark_saved(result_id: int) -> bool:
        """标记结果已保存到数据仓库�?""
        with get_db() as conn:
            conn.execute(
                "UPDATE watch_results SET result_data = 'SAVED:' || result_data WHERE id = ?",
                (result_id,),
            )
            conn.commit()
            return conn.total_changes > 0

    @staticmethod
    def get_saved(page: int = 1, page_size: int = 20, keyword: str = "") -> tuple:
        """获取已保存到数据仓库的结果�?""
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
        """获取数据仓库统计信息�?""
        with get_db() as conn:
            total = conn.execute("SELECT COUNT(*) as cnt FROM watch_results").fetchone()["cnt"]
            success = conn.execute(
                "SELECT COUNT(*) as cnt FROM watch_results WHERE response_status = 200"
            ).fetchone()["cnt"]
            total_size = conn.execute(
                "SELECT COALESCE(SUM(response_size), 0) as s FROM watch_results"
            ).fetchone()["s"]
            source_count = conn.execute(
                "SELECT COUNT(DISTINCT source_id) as cnt FROM watch_results"
            ).fetchone()["cnt"]
        return {
            "total": total,
            "success": success,
            "total_size": total_size,
            "source_count": source_count,
        }
