"""
sensitive_word.py — 敏感词管理 + 内容扫描 + 舆情预警模型

提供敏感词库管理、数据仓库/对话内容扫描、预警记录追踪。
"""
import json
import logging
import re
from datetime import datetime, timezone
from app.models.db import get_db

logger = logging.getLogger(__name__)


class SensitiveWordRepository:
    """敏感词库数据访问类。"""

    # 默认种子敏感词（按严重级别分类）
    SEED_WORDS = [
        # 高危
        ("反动", "高危", 3), ("颠覆", "高危", 3),
        (" terrorist", "高危", 3), ("爆炸物", "高危", 3),
        ("枪支", "高危", 3), ("毒品", "高危", 3),
        ("暗网", "高危", 3), ("入侵", "高危", 3),
        # 中危
        ("赌博", "中危", 2), ("诈骗", "中危", 2),
        ("传销", "中危", 2), ("非法集资", "中危", 2),
        ("泄露隐私", "中危", 2), ("人肉搜索", "中危", 2),
        ("网络攻击", "中危", 2), ("钓鱼", "中危", 2),
        # 低危
        ("投诉", "低危", 1), ("举报", "低危", 1),
        ("维权", "低危", 1), ("争议", "低危", 1),
        ("违规", "低危", 1), ("虚假", "低危", 1),
        ("夸大", "低危", 1), ("误导", "低危", 1),
    ]

    @staticmethod
    def init_table():
        """创建敏感词和预警表（幂等）。"""
        with get_db() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sentiment_sensitive_words (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    word TEXT NOT NULL,
                    category TEXT DEFAULT '低危',
                    severity INTEGER DEFAULT 1,
                    is_enabled INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sentiment_alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_type TEXT NOT NULL,
                    source_id INTEGER DEFAULT NULL,
                    content_preview TEXT DEFAULT '',
                    matched_word TEXT DEFAULT '',
                    severity INTEGER DEFAULT 1,
                    ai_analysis TEXT DEFAULT '',
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_sa_status ON sentiment_alerts(status)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_sa_created ON sentiment_alerts(created_at)
            """)

    @staticmethod
    def seed_default():
        """插入默认敏感词（幂等）。"""
        with get_db() as conn:
            existing = conn.execute(
                "SELECT COUNT(*) as cnt FROM sentiment_sensitive_words"
            ).fetchone()["cnt"]
            if existing == 0:
                for word, category, severity in SensitiveWordRepository.SEED_WORDS:
                    conn.execute(
                        "INSERT INTO sentiment_sensitive_words (word, category, severity, is_enabled) "
                        "VALUES (?, ?, ?, 1)",
                        (word, category, severity),
                    )
                logger.info(f"[种子] 已创建 {len(SensitiveWordRepository.SEED_WORDS)} 个默认敏感词")

    @staticmethod
    def get_all_enabled() -> list:
        """获取所有启用的敏感词。"""
        with get_db() as conn:
            return conn.execute(
                "SELECT * FROM sentiment_sensitive_words WHERE is_enabled = 1 ORDER BY severity DESC"
            ).fetchall()

    @staticmethod
    def get_all(page: int = 1, page_size: int = 50) -> tuple:
        """分页获取敏感词列表。"""
        with get_db() as conn:
            total = conn.execute(
                "SELECT COUNT(*) as cnt FROM sentiment_sensitive_words"
            ).fetchone()["cnt"]
            rows = conn.execute(
                "SELECT * FROM sentiment_sensitive_words ORDER BY severity DESC, id DESC "
                "LIMIT ? OFFSET ?",
                (page_size, (page - 1) * page_size),
            ).fetchall()
            return rows, total

    @staticmethod
    def add(word: str, category: str = "低危", severity: int = 1) -> bool:
        """添加敏感词。"""
        try:
            with get_db() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO sentiment_sensitive_words (word, category, severity) "
                    "VALUES (?, ?, ?)",
                    (word.strip(), category, severity),
                )
                return True
        except Exception as e:
            logger.error(f"添加敏感词失败: {e}")
            return False

    @staticmethod
    def delete(word_id: int) -> bool:
        """删除敏感词。"""
        with get_db() as conn:
            cur = conn.execute("DELETE FROM sentiment_sensitive_words WHERE id = ?", (word_id,))
            return cur.rowcount > 0

    # ════════════════════════════════════════════════════════════
    # 扫描逻辑
    # ════════════════════════════════════════════════════════════

    @staticmethod
    def scan_warehouse(limit: int = 100) -> list:
        """扫描数据仓库标题/摘要匹配敏感词。返回新产生的预警列表。"""
        words = SensitiveWordRepository.get_all_enabled()
        if not words:
            return []

        # 编译正则（不区分大小写）
        patterns = [(w["word"], w["severity"], w["category"])
                    for w in words if w.get("word")]
        alerts = []

        with get_db() as conn:
            rows = conn.execute(
                "SELECT id, title, summary, source_name FROM data_warehouse "
                "ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()

            for row in rows:
                content = f"{row['title'] or ''} {row['summary'] or ''}"
                for word, severity, category in patterns:
                    if re.search(re.escape(word), content, re.IGNORECASE):
                        # 检查是否已存在相同预警
                        existing = conn.execute(
                            "SELECT id FROM sentiment_alerts WHERE source_type = 'warehouse' "
                            "AND source_id = ? AND matched_word = ?",
                            (row["id"], word),
                        ).fetchone()
                        if existing:
                            continue
                        preview = (row["title"] or "")[:200]
                        conn.execute(
                            "INSERT INTO sentiment_alerts "
                            "(source_type, source_id, content_preview, matched_word, severity) "
                            "VALUES (?, ?, ?, ?, ?)",
                            ("warehouse", row["id"], preview, word, severity),
                        )
                        alerts.append({
                            "id": conn.execute("SELECT last_insert_rowid() as id").fetchone()["id"],
                            "source_type": "warehouse",
                            "content_preview": preview,
                            "matched_word": word,
                            "severity": severity,
                            "category": category,
                        })
        return alerts

    @staticmethod
    def scan_conversations(limit: int = 200) -> list:
        """扫描对话消息内容匹配敏感词。"""
        words = SensitiveWordRepository.get_all_enabled()
        if not words:
            return []

        patterns = [(w["word"], w["severity"], w["category"])
                    for w in words if w.get("word")]
        alerts = []

        with get_db() as conn:
            rows = conn.execute(
                "SELECT id, content, conversation_id FROM conversation_messages "
                "WHERE role = 'user' ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()

            for row in rows:
                content = row["content"] or ""
                for word, severity, category in patterns:
                    if re.search(re.escape(word), content, re.IGNORECASE):
                        existing = conn.execute(
                            "SELECT id FROM sentiment_alerts WHERE source_type = 'conversation' "
                            "AND source_id = ? AND matched_word = ?",
                            (row["id"], word),
                        ).fetchone()
                        if existing:
                            continue
                        preview = content[:200]
                        conn.execute(
                            "INSERT INTO sentiment_alerts "
                            "(source_type, source_id, content_preview, matched_word, severity) "
                            "VALUES (?, ?, ?, ?, ?)",
                            ("conversation", row["id"], preview, word, severity),
                        )
                        alerts.append({
                            "id": conn.execute("SELECT last_insert_rowid() as id").fetchone()["id"],
                            "source_type": "conversation",
                            "content_preview": preview,
                            "matched_word": word,
                            "severity": severity,
                            "category": category,
                        })
        return alerts

    @staticmethod
    def scan_all() -> dict:
        """全量扫描（仓库 + 对话）。"""
        w = SensitiveWordRepository.scan_warehouse()
        c = SensitiveWordRepository.scan_conversations()
        return {"warehouse": len(w), "conversation": len(c), "total": len(w) + len(c)}

    # ════════════════════════════════════════════════════════════
    # 预警查询
    # ════════════════════════════════════════════════════════════

    @staticmethod
    def get_alerts(page: int = 1, page_size: int = 20,
                   severity: int = None, status: str = None) -> tuple:
        """获取预警列表。"""
        with get_db() as conn:
            conditions = []
            params = []
            if severity:
                conditions.append("sa.severity >= ?")
                params.append(severity)
            if status:
                conditions.append("sa.status = ?")
                params.append(status)
            where = "WHERE " + " AND ".join(conditions) if conditions else ""

            total = conn.execute(
                f"SELECT COUNT(*) as cnt FROM sentiment_alerts sa {where}",
                params,
            ).fetchone()["cnt"]

            rows = conn.execute(
                f"SELECT sa.* FROM sentiment_alerts sa {where} "
                f"ORDER BY sa.id DESC LIMIT ? OFFSET ?",
                (*params, page_size, (page - 1) * page_size),
            ).fetchall()
            return rows, total

    @staticmethod
    def get_recent_alerts(limit: int = 20) -> list:
        """获取最近的预警（用于大屏滚动）。"""
        with get_db() as conn:
            return conn.execute(
                "SELECT sa.*, "
                "CASE WHEN sa.source_type = 'warehouse' THEN dw.title "
                "     WHEN sa.source_type = 'conversation' THEN cm.content "
                "ELSE '' END as source_detail "
                "FROM sentiment_alerts sa "
                "LEFT JOIN data_warehouse dw ON sa.source_type='warehouse' AND sa.source_id=dw.id "
                "LEFT JOIN conversation_messages cm ON sa.source_type='conversation' AND sa.source_id=cm.id "
                "ORDER BY sa.id DESC LIMIT ?",
                (limit,),
            ).fetchall()

    @staticmethod
    def get_alert_stats() -> dict:
        """获取预警统计数据。"""
        with get_db() as conn:
            total = conn.execute(
                "SELECT COUNT(*) as cnt FROM sentiment_alerts"
            ).fetchone()["cnt"]
            pending = conn.execute(
                "SELECT COUNT(*) as cnt FROM sentiment_alerts WHERE status='pending'"
            ).fetchone()["cnt"]
            high = conn.execute(
                "SELECT COUNT(*) as cnt FROM sentiment_alerts WHERE severity >= 3"
            ).fetchone()["cnt"]
            # 近7天趋势
            trend = conn.execute(
                "SELECT DATE(created_at) as dt, COUNT(*) as cnt, "
                "SUM(CASE WHEN severity >= 3 THEN 1 ELSE 0 END) as high_cnt "
                "FROM sentiment_alerts "
                "WHERE created_at >= DATE('now', '-6 days') "
                "GROUP BY dt ORDER BY dt"
            ).fetchall()
            # 来源分布
            sources = conn.execute(
                "SELECT source_type, COUNT(*) as cnt FROM sentiment_alerts "
                "GROUP BY source_type ORDER BY cnt DESC"
            ).fetchall()
            return {
                "total": total,
                "pending": pending,
                "high_severity": high,
                "trend": [{
                    "date": r["dt"][-5:],
                    "total": r["cnt"],
                    "high": r["high_cnt"],
                } for r in trend],
                "sources": [{"name": r["source_type"], "value": r["cnt"]} for r in sources],
            }

    @staticmethod
    def update_alert_status(alert_id: int, status: str, ai_analysis: str = "") -> bool:
        """更新预警状态和 AI 分析。"""
        with get_db() as conn:
            if ai_analysis:
                cur = conn.execute(
                    "UPDATE sentiment_alerts SET status = ?, ai_analysis = ? WHERE id = ?",
                    (status, ai_analysis, alert_id),
                )
            else:
                cur = conn.execute(
                    "UPDATE sentiment_alerts SET status = ? WHERE id = ?",
                    (status, alert_id),
                )
            return cur.rowcount > 0

    @staticmethod
    def get_alert_detail(alert_id: int) -> dict:
        """获取预警详情（含完整原文）。"""
        with get_db() as conn:
            alert = conn.execute(
                "SELECT * FROM sentiment_alerts WHERE id = ?", (alert_id,)
            ).fetchone()
            if not alert:
                return {}

            result = dict(alert)
            # 加载完整原文
            if alert["source_type"] == "warehouse":
                src = conn.execute(
                    "SELECT title, summary, raw_data, link FROM data_warehouse WHERE id = ?",
                    (alert["source_id"],),
                ).fetchone()
                if src:
                    result["full_content"] = f"{src['title'] or ''}\n{src['summary'] or ''}"
                    result["link"] = src.get("link", "")
            elif alert["source_type"] == "conversation":
                src = conn.execute(
                    "SELECT content, conversation_id FROM conversation_messages WHERE id = ?",
                    (alert["source_id"],),
                ).fetchone()
                if src:
                    result["full_content"] = src["content"] or ""
                    result["conversation_id"] = src.get("conversation_id")
            return result
