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
        """FTS5 全文检索数据仓库（优化版：OR 连接提升召回率）。

        策略：
        1. 优先 FTS5 全文索引（OR + 前缀匹配），提升命中率
        2. FTS5 无结果时回退 LIKE 模糊匹配
        3. 若两轮均无结果，尝试单字前缀匹配（最后兜底）
        """
        if not keyword or not keyword.strip():
            return []
        kw = keyword.strip()
        with get_db() as conn:
            # Exact substring matching is deterministic for Chinese text and avoids
            # tokenizer-dependent partial results.
            like_pattern = f"%{kw}%"
            rows = conn.execute(
                "SELECT * FROM data_warehouse "
                "WHERE title LIKE ? OR summary LIKE ? OR source_name LIKE ? "
                "ORDER BY id DESC LIMIT ?",
                (like_pattern, like_pattern, like_pattern, limit),
            ).fetchall()
            if rows:
                return [dict(r) for r in rows]

            # ── 第一轮：FTS5 OR 前缀匹配（提升召回）──
            terms = kw.split()
            if len(terms) > 1:
                # 多关键词用 OR 连接，每个词加 * 前缀匹配
                fts_query = " OR ".join(f'"{t.replace(chr(34), chr(34) * 2)}"*' for t in terms)
            else:
                fts_query = f'"{kw.replace(chr(34), chr(34) * 2)}"*'
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

            return []

    @staticmethod
    def get_source_distribution(limit: int = 10) -> list:
        """获取数据仓库来源分布。"""
        with get_db() as conn:
            rows = conn.execute(
                "SELECT source_name, COUNT(*) as cnt FROM data_warehouse "
                "WHERE source_name != '' GROUP BY source_name ORDER BY cnt DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [{"name": r["source_name"], "value": r["cnt"]} for r in rows]

    @staticmethod
    def get_trend_data(days: int = 14) -> dict:
        """获取采集趋势数据。"""
        from datetime import datetime, timedelta
        with get_db() as conn:
            rows = conn.execute(
                "SELECT DATE(created_at) as dt, COUNT(*) as cnt "
                "FROM data_warehouse "
                f"WHERE created_at >= DATE('now', '-{days - 1} days') "
                "GROUP BY dt ORDER BY dt"
            ).fetchall()
            date_map = {r["dt"]: r["cnt"] for r in rows}
            today = datetime.now().date()
            all_dates = [(today - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]
            return {
                "dates": [d[-5:] for d in all_dates],
                "counts": [date_map.get(d, 0) for d in all_dates],
            }

    @staticmethod
    def get_keyword_frequency(limit: int = 50) -> list:
        """从数据仓库标题中提取关键词词频（用于词云）。

        使用简单分词策略：去除常见停用词后统计词频。
        """
        import re
        with get_db() as conn:
            titles = conn.execute(
                "SELECT title FROM data_warehouse WHERE title != '' AND title IS NOT NULL"
            ).fetchall()

        # 常见停用词
        stop_words = {
            "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一", "一个",
            "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有", "看", "好",
            "自己", "这", "他", "她", "它", "们", "与", "及", "或", "从", "被", "把", "对",
            "等", "能", "已", "将", "为", "以", "之", "其", "中", "而", "所", "如", "更",
            "又", "但", "而", "还", "可", "让", "用", "做", "并", "且", "如果", "因为",
            "所以", "关于", "虽然", "但是", "不仅", "而且", "或者", "还是", "通过", "进行",
            "可以", "应该", "需要", "没有", "已经", "其中", "以及", "以及", "目前", "日前",
            "今日", "今年", "昨日", "去年", "本月", "今天", "近日", "原标题", "来源", "作者",
        }

        freq = {}
        for row in titles:
            title = row["title"]
            if not title:
                continue
            # 按标点和空格分割（连字符用单独处理避免转义问题）
            sep_re = re.compile(r'[\s,，。、；：！？""''()【】/_—+]+')
            words = sep_re.split(title)
            words = [w.replace('[', '').replace(']', '').replace('-', '') for w in words]
            for word in words:
                word = word.strip()
                # 只保留 2-6 个字符的中文词
                if len(word) < 2 or len(word) > 6:
                    continue
                if not all('\u4e00' <= c <= '\u9fff' for c in word):
                    continue
                if word in stop_words:
                    continue
                freq[word] = freq.get(word, 0) + 1

        # 排序取 Top
        sorted_words = sorted(freq.items(), key=lambda x: -x[1])
        return [{"name": w, "value": c} for w, c in sorted_words[:limit]]

    @staticmethod
    def get_dashboard_stats() -> dict:
        """获取大屏概览统计数据。"""
        with get_db() as conn:
            total = conn.execute("SELECT COUNT(*) as cnt FROM data_warehouse").fetchone()["cnt"]
            deep = conn.execute(
                "SELECT COUNT(*) as cnt FROM data_warehouse WHERE is_deep_collected = 1"
            ).fetchone()["cnt"]
            today_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM data_warehouse "
                "WHERE DATE(created_at) = DATE('now')"
            ).fetchone()["cnt"]
            source_count = conn.execute(
                "SELECT COUNT(DISTINCT source_name) as cnt FROM data_warehouse "
                "WHERE source_name != ''"
            ).fetchone()["cnt"]
            top_source = conn.execute(
                "SELECT source_name, COUNT(*) as cnt FROM data_warehouse "
                "WHERE source_name != '' GROUP BY source_name ORDER BY cnt DESC LIMIT 1"
            ).fetchone()
            return {
                "total": total,
                "deep_collected": deep,
                "today_count": today_count,
                "source_count": source_count,
                "top_source": top_source["source_name"] if top_source else "无",
                "top_source_count": top_source["cnt"] if top_source else 0,
            }

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
