"""
admin_sentiment.py — 舆情大屏控制器（敏感词预警 + AI 风析）

提供敏感词扫描、预警展示、舆情趋势分析和 AI 摘要生成。
"""
import json
import logging
import tornado.web
from app.controllers.admin_base import AdminBaseHandler
from app.models.sensitive_word import SensitiveWordRepository
from app.models.user import UserRepository
from app.utils.security import write_audit_log

logger = logging.getLogger(__name__)


def _redact_conversation_alerts(items, username):
    role = UserRepository.get_user_role(username)
    if role and role.get("is_system") == 1:
        return items
    redacted = []
    for row in items:
        item = dict(row)
        if item.get("source_type") in {"conversation", "live_chat"}:
            item["content_preview"] = "[会话内容仅系统管理员可见]"
            item["source_detail"] = ""
        redacted.append(item)
    return redacted


class AdminSentimentHandler(AdminBaseHandler):
    """舆情大屏页面"""

    @tornado.web.authenticated
    def get(self):
        stats = SensitiveWordRepository.get_alert_stats()
        recent = _redact_conversation_alerts(SensitiveWordRepository.get_recent_alerts(20), self.current_user)
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
        recent = _redact_conversation_alerts(SensitiveWordRepository.get_recent_alerts(50), self.current_user)
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
    """触发敏感词扫描"""

    @tornado.web.authenticated
    def post(self):
        result = SensitiveWordRepository.scan_all()
        from app.services.system_operations import send_alert_notification
        send_alert_notification(result["total"])
        write_audit_log("SENTIMENT_SCAN", self.current_user, "sentiment", f"alerts={result['total']}", self.request.remote_ip or "")
        self.write({"code": 0, "msg": f"扫描完成", "data": result})


class AdminSentimentAlertDetailHandler(AdminBaseHandler):
    """预警详情"""

    @tornado.web.authenticated
    def get(self):
        try:
            alert_id = int(self.get_query_argument("id", 0))
        except (ValueError, TypeError):
            self.write({"code": 1, "msg": "无效的预警ID"})
            return
        detail = SensitiveWordRepository.get_alert_detail(alert_id)
        if not detail:
            self.write({"code": 1, "msg": "预警不存在"})
            return
        detail = _redact_conversation_alerts([detail], self.current_user)[0]
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
        if status not in {"pending", "resolved", "ignored"}:
            self.set_status(400)
            self.write({"code": 1, "msg": "无效的预警状态"})
            return
        SensitiveWordRepository.update_alert_status(alert_id, status)
        write_audit_log("SENTIMENT_ALERT_STATUS", self.current_user, f"alert:{alert_id}", status, self.request.remote_ip or "")
        self.write({"code": 0, "msg": "已更新"})
