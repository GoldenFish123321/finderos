"""
admin_sentiment.py — 舆情大屏控制器（敏感词预警 + AI 风析）

提供敏感词扫描、预警展示、舆情趋势分析和 AI 摘要生成。
"""
import json
import logging
import tornado.web
from app.controllers.admin_base import AdminBaseHandler
from app.models.sensitive_word import SensitiveWordRepository
from app.utils.security import write_audit_log

logger = logging.getLogger(__name__)

ALLOWED_ALERT_STATUSES = {"pending", "resolved", "ignored"}


class AdminSentimentHandler(AdminBaseHandler):
    """舆情大屏页面"""

    @tornado.web.authenticated
    def get(self):
        stats = SensitiveWordRepository.get_alert_stats()
        recent = SensitiveWordRepository.get_recent_alerts(20)
        words, _ = SensitiveWordRepository.get_all(page=1, page_size=200)

        self.render(
            "admin/sentiment.html",
            title="舆情大屏 — 瞭望与问数系统",
            username=self.current_user,
            xsrf_token=self.xsrf_token.decode() if isinstance(self.xsrf_token, bytes) else self.xsrf_token,
            stats=stats,
            recent_alerts=recent,
            words=[w["word"] for w in words if w.get("is_enabled")],
        )


class AdminSentimentApiHandler(AdminBaseHandler):
    """舆情数据 JSON API"""

    @tornado.web.authenticated
    def get(self):
        stats = SensitiveWordRepository.get_alert_stats()
        recent = SensitiveWordRepository.get_recent_alerts(50)
        # 序列化 datetime 对象
        items = []
        for r in recent:
            item = dict(r)
            for k, v in item.items():
                if hasattr(v, 'isoformat'):
                    item[k] = v.isoformat()
            items.append(item)

        self.write({
            "code": 0,
            "data": {
                "stats": stats,
                "recent_alerts": items,
            }
        })


class AdminSentimentScanHandler(AdminBaseHandler):
    """触发敏感词扫描 + AI 自动分析"""

    @tornado.web.authenticated
    def post(self):
        result = SensitiveWordRepository.scan_and_analyze_all()
        write_audit_log(
            action="SENTIMENT_SCAN",
            username=self.current_user,
            target="sentiment:scan",
            detail=f"扫描+分析完成，新预警 {result.get('scan', {}).get('total', 0)} 条",
            client_ip=self.request.remote_ip or "",
        )
        self.write({"code": 0, "msg": f"扫描+分析完成", "data": result})


class AdminSentimentAnalyzeHandler(AdminBaseHandler):
    """对未分析预警触发 AI 语义分析"""

    @tornado.web.authenticated
    def post(self):
        try:
            limit = int(self.get_body_argument("limit", 10))
        except (ValueError, TypeError):
            limit = 10
        results = SensitiveWordRepository.analyze_pending_alerts(limit=limit)
        self.write({"code": 0, "msg": f"已分析 {len(results)} 条预警", "data": results})


class AdminSentimentAlertDetailHandler(AdminBaseHandler):
    """预警详情"""

    @tornado.web.authenticated
    def get(self):
        try:
            alert_id = int(self.get_query_argument("id", 0))
        except (ValueError, TypeError):
            self.write({"code": 1, "msg": "无效的预警ID"})
            return
        detail = SensitiveWordRepository.get_alert_detail(alert_id, username=self.current_user)
        if not detail:
            self.write({"code": 1, "msg": "预警不存在"})
            return
        self.write({"code": 0, "data": detail})


class AdminSentimentResolveHandler(AdminBaseHandler):
    """标记预警为已处理"""

    @tornado.web.authenticated
    def post(self):
        try:
            alert_id = int(self.get_body_argument("id", 0))
        except (ValueError, TypeError):
            self.write({"code": 1, "msg": "无效的预警ID"})
            return
        status = self.get_body_argument("status", "resolved")
        if status not in ALLOWED_ALERT_STATUSES:
            self.write({"code": 1, "msg": f"无效的状态值: {status}"})
            return
        ai_analysis = self.get_body_argument("ai_analysis", "")
        SensitiveWordRepository.update_alert_status(alert_id, status, ai_analysis)
        write_audit_log(
            action="SENTIMENT_RESOLVE",
            username=self.current_user,
            target=f"sentiment:alert:{alert_id}",
            detail=f"预警状态 → {status}",
            client_ip=self.request.remote_ip or "",
        )
        self.write({"code": 0, "msg": "已更新"})
