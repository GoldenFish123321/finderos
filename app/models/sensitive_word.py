"""
sensitive_word.py — 敏感词管理 + 内容扫描 + 舆情预警模型

提供敏感词库管理、数据仓库/对话内容扫描、预警记录追踪。
"""
import json
import hashlib
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
    def init_table(conn=None):
        """创建敏感词和预警表（幂等）。

        ``init_db()`` 已经持有一个 SQLite 写连接时会传入该连接，避免
        在同一数据库初始化事务中再次打开连接导致 ``database is locked``。
        """
        def _create_tables(active_conn):
            active_conn.execute("""
                CREATE TABLE IF NOT EXISTS sentiment_sensitive_words (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    word TEXT NOT NULL UNIQUE,
                    category TEXT DEFAULT '低危',
                    severity INTEGER DEFAULT 1,
                    is_enabled INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            active_conn.execute("""
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
            active_conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_sa_status ON sentiment_alerts(status)
            """)
            active_conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_sa_created ON sentiment_alerts(created_at)
            """)
            active_conn.execute(
                "DELETE FROM sentiment_sensitive_words WHERE id NOT IN "
                "(SELECT MIN(id) FROM sentiment_sensitive_words GROUP BY word)"
            )
            active_conn.execute(
                "DELETE FROM sentiment_alerts WHERE id NOT IN "
                "(SELECT MIN(id) FROM sentiment_alerts GROUP BY source_type, source_id, matched_word)"
            )
            active_conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_sensitive_word ON sentiment_sensitive_words(word)"
            )
            active_conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_sentiment_alert_source "
                "ON sentiment_alerts(source_type, source_id, matched_word)"
            )

        if conn is not None:
            _create_tables(conn)
            return

        with get_db() as standalone_conn:
            _create_tables(standalone_conn)

    @staticmethod
    def seed_default():
        """插入默认敏感词（幂等）。"""
        with get_db() as conn:
            for word, category, severity in SensitiveWordRepository.SEED_WORDS:
                conn.execute(
                    "INSERT OR IGNORE INTO sentiment_sensitive_words (word, category, severity, is_enabled) "
                    "VALUES (?, ?, ?, 1)",
                    (word, category, severity),
                )

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
        if not word or len(word.strip()) < 1:
            return False
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
                        cursor = conn.execute(
                            "INSERT OR IGNORE INTO sentiment_alerts "
                            "(source_type, source_id, content_preview, matched_word, severity) "
                            "VALUES (?, ?, ?, ?, ?)",
                            ("warehouse", row["id"], preview, word, severity),
                        )
                        if cursor.rowcount == 0:
                            continue
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
                        cursor = conn.execute(
                            "INSERT OR IGNORE INTO sentiment_alerts "
                            "(source_type, source_id, content_preview, matched_word, severity) "
                            "VALUES (?, ?, ?, ?, ?)",
                            ("conversation", row["id"], preview, word, severity),
                        )
                        if cursor.rowcount == 0:
                            continue
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

    @staticmethod
    def match_content(content: str) -> dict | None:
        for item in SensitiveWordRepository.get_all_enabled():
            word = item.get("word", "")
            if word and re.search(re.escape(word), content or "", re.IGNORECASE):
                return dict(item)
        return None

    @staticmethod
    def record_user_alert(content: str, username: str = "") -> bool:
        match = SensitiveWordRepository.match_content(content)
        if not match:
            return False
        stable_id = int.from_bytes(
            hashlib.sha256(f"{username}\0{content}".encode("utf-8")).digest()[:8], "big"
        ) & 0x7FFFFFFFFFFFFFFF
        with get_db() as conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO sentiment_alerts "
                "(source_type, source_id, content_preview, matched_word, severity) "
                "VALUES ('live_chat', ?, ?, ?, ?)",
                (stable_id, (content or "")[:200], match["word"], match.get("severity", 1)),
            )
        return True

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
        """获取最近的预警（用于大屏滚动）。

        安全：不再 JOIN conversation_messages，仅使用 content_preview 前50字符，
        避免在预警列表中泄露完整对话内容。
        """
        with get_db() as conn:
            rows = conn.execute(
                "SELECT sa.* FROM sentiment_alerts sa "
                "ORDER BY sa.id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            # 截断 content_preview 到 50 字符，移除 source_detail 泄露风险
            result = []
            for row in rows:
                item = dict(row)
                preview = (item.get("content_preview") or "")[:50]
                item["content_preview"] = preview
                result.append(item)
            return result

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
    def get_alert_detail(alert_id: int, username: str = "") -> dict:
        """获取预警详情（含完整原文）。

        安全：非对话创建者只能看到脱敏内容（仅显示匹配词上下文），
        防止通过预警详情接口泄露他人隐私对话。
        """
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
                    "SELECT cm.content, cm.conversation_id "
                    "FROM conversation_messages cm WHERE cm.id = ?",
                    (alert["source_id"],),
                ).fetchone()
                if src:
                    conv_id = src.get("conversation_id")
                    # 检查请求者是否为对话创建者
                    is_creator = False
                    if username and conv_id:
                        conv = conn.execute(
                            "SELECT username FROM conversations WHERE id = ?",
                            (conv_id,),
                        ).fetchone()
                        if conv and conv["username"] == username:
                            is_creator = True

                    if is_creator:
                        result["full_content"] = src["content"] or ""
                    else:
                        # 非创建者：只显示脱敏片段（匹配词周围 ±30 字符）
                        raw = src["content"] or ""
                        matched = alert.get("matched_word", "")
                        if matched and matched in raw:
                            idx = raw.find(matched)
                            start = max(0, idx - 30)
                            end = min(len(raw), idx + len(matched) + 30)
                            snippet = raw[start:end]
                            result["full_content"] = f"[脱敏] ...{snippet}..."
                        else:
                            result["full_content"] = "[脱敏] 无权查看完整内容"
                    result["conversation_id"] = conv_id
            return result

    # ════════════════════════════════════════════════════════════
    # AI 语义分析
    # ════════════════════════════════════════════════════════════

    @staticmethod
    def analyze_alert_with_ai(alert_id: int) -> dict:
        """调用 AI 模型对预警上下文进行深度语义分析。

        分析流程：
        1. 获取预警详情（含完整原文）
        2. 使用系统默认 AI 模型进行风析
        3. 将分析结果写入 ai_analysis + 更新状态
        4. 返回分析结果
        """
        detail = SensitiveWordRepository.get_alert_detail(alert_id)
        if not detail:
            return {"error": "预警不存在"}

        full_content = detail.get("full_content", detail.get("content_preview", ""))
        matched_word = detail.get("matched_word", "")
        source_type = detail.get("source_type", "")

        if not full_content:
            return {"error": "无可分析的原文内容"}

        try:
            from app.models.ai_model import AiModelRepository
            model = AiModelRepository.get_default(include_api_key=True)
            if not model or not model.get("api_key"):
                # 无 API Key 时使用关键词匹配增强的本地分析
                analysis = SensitiveWordRepository._local_analyze(
                    full_content, matched_word, source_type
                )
                SensitiveWordRepository.update_alert_status(
                    alert_id, "analyzed", analysis
                )
                return {"analyzed": True, "content": analysis, "mode": "local"}

            # ── 构建 AI 分析 Prompt ──
            prompt_text = (
                f"你是一个专业的舆情安全分析系统。请对以下内容进行安全风险评估，"
                f"要求输出 JSON 格式（只输出 JSON，不要其他文字）。\n\n"
                f"## 原文内容\n{full_content[:2000]}\n\n"
                f"## 匹配的敏感词\n{matched_word}\n\n"
                f"## 来源类型\n{source_type}\n\n"
                f"请输出以下 JSON 字段：\n"
                f'{{"risk_level": "high/medium/low", "analysis": "分析说明（50-200字）", '
                f'"suggestion": "建议操作"}}'
            )

            # ── 调用 LLM API ──
            from app.utils.safe_http import safe_http_request
            import json as _json

            api_base = (model.get("api_base") or "https://api.openai.com/v1").rstrip("/")
            api_key = model.get("api_key", "")
            model_name = model.get("model_name") or model.get("name")

            payload = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": "你是一个舆情安全分析专家。始终以 JSON 格式输出。"},
                    {"role": "user", "content": prompt_text},
                ],
                "temperature": 0.3,
                "max_tokens": 1024,
            }

            payload_bytes = _json.dumps(payload, ensure_ascii=False).encode("utf-8")
            safe_url = api_base.rstrip("/") + "/chat/completions"
            safe_headers = {
                "Content-Type": "application/json; charset=utf-8",
                "Authorization": f"Bearer {api_key}",
            }

            response = safe_http_request(
                safe_url, method="POST", headers=safe_headers,
                body=payload_bytes, timeout=30, max_bytes=256 * 1024,
            )

            if response.status >= 400:
                raise Exception(f"API 返回 HTTP {response.status}")

            raw = response.body.decode("utf-8", errors="replace")
            resp_data = _json.loads(raw)
            content = resp_data.get("choices", [{}])[0].get("message", {}).get("content", "")

            # 尝试从回复中提取 JSON（支持嵌套花括号和 markdown 代码块）
            analysis_json = None
            content_clean = content.strip()
            try:
                analysis_json = _json.loads(content_clean)
            except (_json.JSONDecodeError, TypeError):
                import re as _re
                # 先剥离 markdown 代码块标记
                code_match = _re.search(
                    r'```(?:json)?\s*\n?(.*?)```', content_clean, _re.DOTALL
                )
                if code_match:
                    candidate = code_match.group(1).strip()
                    try:
                        analysis_json = _json.loads(candidate)
                    except (_json.JSONDecodeError, TypeError):
                        pass
                # 括号计数法提取最外层 JSON
                if analysis_json is None:
                    brace_depth = 0
                    start = -1
                    for i, ch in enumerate(content_clean):
                        if ch == '{':
                            if start == -1:
                                start = i
                            brace_depth += 1
                        elif ch == '}':
                            brace_depth -= 1
                            if brace_depth == 0 and start != -1:
                                try:
                                    analysis_json = _json.loads(
                                        content_clean[start:i + 1]
                                    )
                                except (_json.JSONDecodeError, TypeError):
                                    pass
                                start = -1
                                if analysis_json:
                                    break

            if analysis_json:
                risk = str(analysis_json.get("risk_level", "medium")).lower()
                analysis_text = analysis_json.get("analysis", content[:500])
                suggestion = analysis_json.get("suggestion", "")
                structured = _json.dumps({
                    "risk_level": risk, "analysis": analysis_text,
                    "suggestion": suggestion,
                }, ensure_ascii=False)
                # 根据 AI 风险评估更新严重级别
                severity_map = {"high": 3, "medium": 2, "low": 1}
                new_severity = severity_map.get(risk, 2)
                with get_db() as conn:
                    conn.execute(
                        "UPDATE sentiment_alerts SET ai_analysis = ?, severity = ?, "
                        "status = 'analyzed' WHERE id = ?",
                        (structured, new_severity, alert_id),
                    )
                return {"analyzed": True, "content": structured, "mode": "ai"}
            else:
                analysis = f"[AI分析] 匹配敏感词「{matched_word}」，AI 未能结构化解析。原始回复: {content[:500]}"
                SensitiveWordRepository.update_alert_status(alert_id, "analyzed", analysis)
                return {"analyzed": True, "content": analysis, "mode": "ai_raw"}

        except Exception as e:
            logger.warning(f"AI 分析预警 {alert_id} 失败: {e}")
            # 回退到本地分析
            analysis = SensitiveWordRepository._local_analyze(
                full_content, matched_word, source_type
            )
            SensitiveWordRepository.update_alert_status(alert_id, "analyzed", analysis)
            return {"analyzed": True, "content": analysis, "mode": "local_fallback"}

    @staticmethod
    def _local_analyze(full_content: str, matched_word: str, source_type: str) -> str:
        """本地规则分析（无 API Key 时的回退方案）。"""
        import json as _json
        content_lower = full_content.lower()

        # 高风险关键词扩展
        high_risk_signals = ["银行卡", "密码", "转账", "验证码", "身份证",
                             "手机号", "住址", "账号", "登录密码", "支付密码"]
        low_risk_signals = ["举报", "投诉", "反馈", "建议", "咨询", "请问"]

        high_hits = sum(1 for s in high_risk_signals if s in content_lower)
        low_hits = sum(1 for s in low_risk_signals if s in content_lower)

        if high_hits >= 2:
            risk_level = "high"
            note = f"上下文包含 {high_hits} 个敏感信号词，建议人工复核"
        elif high_hits >= 1:
            risk_level = "medium"
            note = f"上下文含 {high_hits} 个敏感信号词，需关注"
        else:
            risk_level = "low"
            note = "上下文未发现额外敏感信号，常规提醒"

        return _json.dumps({
            "risk_level": risk_level,
            "analysis": f"匹配敏感词「{matched_word}」，来源 {source_type}。{note}",
            "suggestion": "建议查看原文后判断" if risk_level != "low" else "可标记为已处理",
        }, ensure_ascii=False)

    @staticmethod
    def analyze_pending_alerts(limit: int = 10) -> list:
        """批量分析所有未分析的预警。返回分析结果列表。"""
        results = []
        with get_db() as conn:
            alerts = conn.execute(
                "SELECT id FROM sentiment_alerts WHERE status = 'pending' "
                "ORDER BY severity DESC, id DESC LIMIT ?", (limit,)
            ).fetchall()
        for alert in alerts:
            try:
                r = SensitiveWordRepository.analyze_alert_with_ai(alert["id"])
                results.append({"alert_id": alert["id"], **r})
            except Exception as e:
                logger.warning(f"批量分析预警 {alert['id']} 异常: {e}")
        return results

    @staticmethod
    def scan_and_analyze_all() -> dict:
        """全量扫描 + AI 自动分析。"""
        scan = SensitiveWordRepository.scan_all()
        analysis = SensitiveWordRepository.analyze_pending_alerts(limit=20)
        return {
            "scan": scan,
            "analysis_count": len(analysis),
            "analysis": analysis,
        }
