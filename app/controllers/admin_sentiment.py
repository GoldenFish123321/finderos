"""
admin_sentiment.py — 舆情大屏控制器（敏感词预警 + AI 风析）

提供敏感词扫描、预警展示、舆情趋势分析和 AI 摘要生成。
"""
import json
import logging
import tornado.web
from app.controllers.admin_base import AdminBaseHandler
from app.models.sensitive_word import SensitiveWordRepository

logger = logging.getLogger(__name__)


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
    """触发敏感词扫描"""

    @tornado.web.authenticated
    def post(self):
        result = SensitiveWordRepository.scan_all()
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
        SensitiveWordRepository.update_alert_status(alert_id, status)
        self.write({"code": 0, "msg": "已更新"})
