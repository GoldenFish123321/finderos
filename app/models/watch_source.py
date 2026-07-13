"""
watch_source.py �?watch_sources 表的仓储对象

瞭源管理：管理数据采集的来源和请求规则（RequestHeaders + URL 模板）�?"""
import json
import sqlite3
from app.models.db import get_db


class WatchSourceRepository:
    """瞭望源数据访问类"""

    @staticmethod
    def get_all(page: int = 1, page_size: int = 20, keyword: str = "") -> tuple:
        """分页查询瞭望源列表，返回 (rows, total)�?""
        with get_db() as conn:
            if keyword:
                where = "WHERE name LIKE ?"
                params = (f"%{keyword}%",)
            else:
                where = ""
                params = ()
            total = conn.execute(
                f"SELECT COUNT(*) as cnt FROM watch_sources {where}", params
            ).fetchone()["cnt"]
            rows = conn.execute(
                f"SELECT * FROM watch_sources {where} "
                f"ORDER BY sort_order ASC, id ASC LIMIT ? OFFSET ?",
                (*params, page_size, (page - 1) * page_size),
            ).fetchall()
        return rows, total

    @staticmethod
    def get_enabled() -> list:
        """获取所有启用的瞭望源�?""
        with get_db() as conn:
            return conn.execute(
                "SELECT * FROM watch_sources WHERE is_enabled = 1 ORDER BY sort_order ASC"
            ).fetchall()

    @staticmethod
    def get_by_id(source_id: int):
        """根据 ID 查询瞭望源�?""
        with get_db() as conn:
            return conn.execute(
                "SELECT * FROM watch_sources WHERE id = ?", (source_id,)
            ).fetchone()

    @staticmethod
    def create(name: str, description: str, url_template: str,
               request_headers: str = "{}", sort_order: int = 0) -> bool:
        """创建瞭望源�?""
        try:
            json.loads(request_headers)  # 校验 JSON 格式
        except json.JSONDecodeError:
            return False
        try:
            with get_db() as conn:
                conn.execute(
                    "INSERT INTO watch_sources (name, description, url_template, request_headers, sort_order) "
                    "VALUES (?, ?, ?, ?, ?)",
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
        """更新瞭望源�?""
        try:
            json.loads(request_headers)  # 校验 JSON 格式
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
        """删除瞭望源�?""
        with get_db() as conn:
            conn.execute("DELETE FROM watch_sources WHERE id = ?", (source_id,))
            conn.commit()
            return True

    @staticmethod
    def toggle_enabled(source_id: int) -> int:
        """切换启用/禁用状态，返回新状态�?""
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
    def get_count() -> int:
        """获取瞭望源总数�?""
        with get_db() as conn:
            return conn.execute("SELECT COUNT(*) as cnt FROM watch_sources").fetchone()["cnt"]

    @staticmethod
    def get_headers(source_id: int) -> dict:
        """获取瞭望源的请求头（JSON �?dict）�?""
        row = WatchSourceRepository.get_by_id(source_id)
        if not row:
            return {}
        try:
            return json.loads(row["request_headers"])
        except (json.JSONDecodeError, TypeError):
            return {}
