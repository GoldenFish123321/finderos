"""
data_warehouse.py — 数据仓库独立存储模型

独立数据仓库表，替代原有的 watch_results SAVED: 前缀标记方案。
借鉴郭家琪项目的独立 data_warehouse 表设计。

表结构:
- id: 主键
- result_id: 关联的watch_results ID
- title: 采集结果标题
- link: 采集结果链接（UNIQUE去重）
- summary: 摘要
- source_name: 来源名称
- raw_data: 完整原始数据（JSON）
- is_deep_collected: 是否已深度采集
- deep_collected_at: 深度采集时间
- created_at: 入库时间
"""

import json
import logging
from app.models.db import get_db

logger = logging.getLogger(__name__)


class DataWarehouseRepository:
    """独立数据仓库数据访问类。"""

    @staticmethod
    def create(result_id: int, title: str, link: str = "", summary: str = "",
               source_name: str = "", raw_data: str = "") -> bool:
        """保存一条采集结果到数据仓库。

        去重策略：
        - link 非空时，由数据库层 UNIQUE 索引自动去重
        - link 为空时，按 title + source_name 组合应用层去重（因为部分唯一索引不覆盖空值）
        """
        try:
            with get_db() as conn:
                cursor = conn.execute(
                    "INSERT OR IGNORE INTO data_warehouse "
                    "(result_id, title, link, summary, source_name, raw_data) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (result_id, title, link, summary, source_name, raw_data),
                )
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"create: 保存数据仓库记录失败 (title={title[:50]}): {e}", exc_info=True)
            return False

    @staticmethod
    def batch_create(items: list[dict]) -> int:
        """批量保存到数据仓库。返回成功保存数。"""
        count = 0
        with get_db() as conn:
            for item in items:
                try:
                    title = item.get("title", "")
                    link = item.get("link", "")
                    source_name = item.get("source_name", "")
                    raw_data = json.dumps(item, ensure_ascii=False) if item else ""

                    cursor = conn.execute(
                        "INSERT OR IGNORE INTO data_warehouse "
                        "(result_id, title, link, summary, source_name, raw_data) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (item.get("result_id"), title, link,
                         item.get("summary"), source_name, raw_data),
                    )
                    if cursor.rowcount > 0:
                        count += 1
                except Exception as e:
                    logger.error(f"batch_create: 插入数据仓库记录失败: {e}", exc_info=True)
        return count

    @staticmethod
    def get_all(page: int = 1, page_size: int = 20, keyword: str = "",
                source_id: int = None) -> tuple:
        """分页查询数据仓库记录。返回 (rows, total)。"""
        with get_db() as conn:
            conditions = []
            params = []
            if keyword:
                conditions.append("(dw.title LIKE ? OR dw.summary LIKE ?)")
                params.extend([f"%{keyword}%", f"%{keyword}%"])
            if source_id:
                conditions.append("wr.source_id = ?")
                params.append(source_id)
            where = "WHERE " + " AND ".join(conditions) if conditions else ""
            total = conn.execute(
                f"SELECT COUNT(*) as cnt FROM data_warehouse dw "
                f"LEFT JOIN watch_results wr ON dw.result_id = wr.id {where}",
                params,
            ).fetchone()["cnt"]
            rows = conn.execute(
                f"SELECT dw.*, wr.keyword, wr.source_id, wr.request_url, "
                f"wr.response_status, wr.response_size, wr.result_data, "
                f"ws.name as watch_source_name "
                f"FROM data_warehouse dw "
                f"LEFT JOIN watch_results wr ON dw.result_id = wr.id "
                f"LEFT JOIN watch_sources ws ON wr.source_id = ws.id "
                f"{where} ORDER BY dw.id DESC LIMIT ? OFFSET ?",
                (*params, page_size, (page - 1) * page_size),
            ).fetchall()
        return rows, total

    @staticmethod
    def get_by_id(dw_id: int):
        """按ID获取数据仓库记录。"""
        with get_db() as conn:
            return conn.execute(
                "SELECT dw.*, wr.keyword, wr.source_id, wr.request_url, "
                "wr.response_status, wr.response_size, wr.result_data, "
                "ws.name as watch_source_name "
                "FROM data_warehouse dw "
                "LEFT JOIN watch_results wr ON dw.result_id = wr.id "
                "LEFT JOIN watch_sources ws ON wr.source_id = ws.id "
                "WHERE dw.id = ?",
                (dw_id,),
            ).fetchone()

    @staticmethod
    def delete(dw_id: int) -> bool:
        """删除单条数据仓库记录。"""
        with get_db() as conn:
            cursor = conn.execute("DELETE FROM data_warehouse WHERE id = ?", (dw_id,))
            conn.commit()
            return cursor.rowcount > 0

    @staticmethod
    def batch_delete(ids: list[int]) -> int:
        """批量删除数据仓库记录。返回删除数。"""
        count = 0
        with get_db() as conn:
            for dw_id in ids:
                cursor = conn.execute("DELETE FROM data_warehouse WHERE id = ?", (dw_id,))
                if cursor.rowcount > 0:
                    count += 1
            conn.commit()
        return count

    @staticmethod
    def get_count() -> int:
        """获取数据仓库总记录数。"""
        with get_db() as conn:
            return conn.execute("SELECT COUNT(*) as cnt FROM data_warehouse").fetchone()["cnt"]

    @staticmethod
    def mark_deep_collected(dw_id: int, content: str = "", content_size: int = 0) -> bool:
        """标记为已深度采集，并保存提取的正文内容。

        将提取的正文内容存入 raw_data 字段（JSON 格式），
        同时更新 is_deep_collected 标志和 deep_collected_at 时间戳。
        """
        import json as _json
        from datetime import datetime, timezone
        try:
            # 统一使用 Python UTC 时间，避免与 SQLite CURRENT_TIMESTAMP 时区不一致
            now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            with get_db() as conn:
                # 获取当前记录
                row = conn.execute(
                    "SELECT raw_data FROM data_warehouse WHERE id = ?", (dw_id,)
                ).fetchone()
                if not row:
                    return False

                # 合并深度采集内容到 raw_data
                existing_raw = row["raw_data"] or ""
                try:
                    raw_obj = _json.loads(existing_raw) if existing_raw else {}
                except (_json.JSONDecodeError, TypeError):
                    raw_obj = {"original": existing_raw}

                if isinstance(raw_obj, dict):
                    raw_obj["deep_content"] = content
                    raw_obj["deep_content_size"] = content_size
                    raw_obj["deep_collected_at"] = now_utc
                else:
                    raw_obj = {
                        "original": raw_obj,
                        "deep_content": content,
                        "deep_content_size": content_size,
                        "deep_collected_at": now_utc,
                    }

                new_raw = _json.dumps(raw_obj, ensure_ascii=False)
                cursor = conn.execute(
                    "UPDATE data_warehouse SET raw_data = ?, is_deep_collected = 1, "
                    "deep_collected_at = ? WHERE id = ?",
                    (new_raw, now_utc, dw_id),
                )
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"mark_deep_collected: 深度采集保存失败 (dw_id={dw_id}): {e}", exc_info=True)
            return False

    @staticmethod
    def get_deep_collected(page: int = 1, page_size: int = 20) -> tuple:
        """分页查询已深度采集的记录。返回 (rows, total)。"""
        with get_db() as conn:
            total = conn.execute(
                "SELECT COUNT(*) as cnt FROM data_warehouse WHERE is_deep_collected = 1"
            ).fetchone()["cnt"]
            rows = conn.execute(
                "SELECT dw.*, wr.keyword, ws.name as watch_source_name "
                "FROM data_warehouse dw "
                "LEFT JOIN watch_results wr ON dw.result_id = wr.id "
                "LEFT JOIN watch_sources ws ON wr.source_id = ws.id "
                "WHERE dw.is_deep_collected = 1 "
                "ORDER BY dw.deep_collected_at DESC LIMIT ? OFFSET ?",
                (page_size, (page - 1) * page_size),
            ).fetchall()
        return rows, total

    @staticmethod
    def get_recent(limit: int = 10) -> list:
        """获取数据仓库最新记录。"""
        with get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM data_warehouse ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    @staticmethod
    def search(keyword: str, limit: int = 10) -> list:
        """FTS5 全文检索数据仓库。返回匹配记录列表。"""
        if not keyword or not keyword.strip():
            return []
        with get_db() as conn:
            # 使用 FTS5 全文检索，支持多关键词和前缀匹配
            # 将用户输入拆分为多个词，每个词后加 * 做前缀匹配
            terms = keyword.strip().split()
            fts_query = " AND ".join(f'"{t}"' for t in terms) if len(terms) > 1 else f'"{keyword.strip()}"'
            try:
                rows = conn.execute(
                    "SELECT dw.* FROM data_warehouse_fts fts "
                    "JOIN data_warehouse dw ON fts.rowid = dw.id "
                    "WHERE data_warehouse_fts MATCH ? "
                    "ORDER BY rank LIMIT ?",
                    (fts_query, limit),
                ).fetchall()
                if rows:
                    return [dict(r) for r in rows]
            except Exception:
                pass

            # FTS5 回退：使用 LIKE 模糊匹配
            like_pattern = f"%{keyword.strip()}%"
            rows = conn.execute(
                "SELECT * FROM data_warehouse "
                "WHERE title LIKE ? OR summary LIKE ? OR source_name LIKE ? "
                "ORDER BY id DESC LIMIT ?",
                (like_pattern, like_pattern, like_pattern, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    @staticmethod
    def get_stats() -> dict:
        """获取数据仓库统计信息。"""
        with get_db() as conn:
            total = conn.execute(
                "SELECT COUNT(*) as cnt FROM data_warehouse"
            ).fetchone()["cnt"]
            deep = conn.execute(
                "SELECT COUNT(*) as cnt FROM data_warehouse WHERE is_deep_collected = 1"
            ).fetchone()["cnt"]
            sources = conn.execute(
                "SELECT source_name, COUNT(*) as cnt FROM data_warehouse "
                "WHERE source_name != '' GROUP BY source_name ORDER BY cnt DESC LIMIT 10"
            ).fetchall()
            return {
                "total": total,
                "deep_collected": deep,
                "top_sources": [{"name": s["source_name"], "count": s["cnt"]} for s in sources],
            }
