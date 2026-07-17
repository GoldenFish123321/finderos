"""
admin_home.py — 管理后台 Dashboard 控制器

后台首页展示概览数据、统计卡片和 ECharts 趋势图表。
"""
import tornado.web
from app.controllers.admin_base import AdminBaseHandler
from app.models.user import UserRepository
from app.models.role import RoleRepository
from app.models.function import FunctionRepository
from app.models.watch_source import WatchSourceRepository
from app.models.watch_result import WatchResultRepository
from app.models.data_warehouse import DataWarehouseRepository
from app.models.ai_model import AiModelRepository
from app.models.db import get_db
from app.utils.security import sanitize_html


class AdminIndexHandler(AdminBaseHandler):
    """管理后台 Dashboard"""

    @tornado.web.authenticated
    def get(self):
        user_count = UserRepository.get_user_count()
        role_count = RoleRepository.get_count()
        func_count = FunctionRepository.get_count()
        source_count = WatchSourceRepository.get_count()
        result_count = WatchResultRepository.get_count()
        warehouse_count = DataWarehouseRepository.get_count()
        model_count = AiModelRepository.get_count(model_scope="admin", owner_username="")
        result_stats = WatchResultRepository.get_stats()
        model_stats = AiModelRepository.get_stats(model_scope="admin", owner_username="")

        # ── ECharts 图表数据（传递 Python 对象，模板中使用 json_encode 序列化）──
        source_distribution = self._get_source_distribution()
        collect_trend = self._get_collect_trend()
        deep_stats = DataWarehouseRepository.get_stats()

        self.render(
            "admin/index.html",
            title="管理后台 — 瞭望与问数系统",
            username=self.current_user,
            user_count=user_count,
            role_count=role_count,
            func_count=func_count,
            source_count=source_count,
            result_count=result_count,
            warehouse_count=warehouse_count,
            model_count=model_count,
            result_stats=result_stats,
            model_stats=model_stats,
            source_distribution=source_distribution,
            collect_trend=collect_trend,
            deep_collected=deep_stats.get("deep_collected", 0),
            deep_total=deep_stats.get("total", 0),
        )

    @staticmethod
    def _get_source_distribution() -> list:
        """获取数据仓库来源分布（Top 8）。"""
        with get_db() as conn:
            rows = conn.execute(
                "SELECT source_name, COUNT(*) as cnt FROM data_warehouse "
                "WHERE source_name != '' GROUP BY source_name "
                "ORDER BY cnt DESC LIMIT 8"
            ).fetchall()
            return [{"name": sanitize_html(r["source_name"] or "未知"), "value": r["cnt"]} for r in rows]

    @staticmethod
    def _get_collect_trend() -> dict:
        """获取近7天每日采集量趋势。"""
        with get_db() as conn:
            rows = conn.execute(
                "SELECT DATE(created_at) as dt, COUNT(*) as cnt "
                "FROM data_warehouse "
                "WHERE created_at >= DATE('now', '-6 days') "
                "GROUP BY dt ORDER BY dt"
            ).fetchall()
            dates = [r["dt"] for r in rows]
            counts = [r["cnt"] for r in rows]
            # 补全缺失日期
            from datetime import datetime, timedelta
            today = datetime.now().date()
            all_dates = [(today - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
            date_map = dict(zip(dates, counts))
            return {
                "dates": all_dates,
                "counts": [date_map.get(d, 0) for d in all_dates],
            }


class AdminDashboardHandler(AdminBaseHandler):
    """管理侧数智大屏 — 3D 地球 + 词云 + 数据可视化"""

    @tornado.web.authenticated
    def get(self):
        stats = DataWarehouseRepository.get_dashboard_stats()
        source_dist = DataWarehouseRepository.get_source_distribution(8)
        source_geo = DataWarehouseRepository.get_dashboard_source_geo(12)
        trend = DataWarehouseRepository.get_trend_data(14)
        keywords = DataWarehouseRepository.get_keyword_frequency(50)
        recent_items = DataWarehouseRepository.get_recent_dashboard_items(8)

        self.render(
            "admin/dashboard.html",
            title="数智大屏 — 瞭望与问数系统",
            username=self.current_user,
            xsrf_token=self.xsrf_token.decode() if isinstance(self.xsrf_token, bytes) else self.xsrf_token,
            stats=stats,
            source_distribution=source_dist,
            source_geo=source_geo,
            trend=trend,
            keywords=keywords,
            recent_items=recent_items,
        )


class AdminDashboardApiHandler(AdminBaseHandler):
    """大屏数据 JSON API — 供前端异步刷新"""

    @tornado.web.authenticated
    def get(self):
        stats = DataWarehouseRepository.get_dashboard_stats()
        source_dist = DataWarehouseRepository.get_source_distribution(8)
        source_geo = DataWarehouseRepository.get_dashboard_source_geo(12)
        trend = DataWarehouseRepository.get_trend_data(14)
        keywords = DataWarehouseRepository.get_keyword_frequency(50)
        recent_items = DataWarehouseRepository.get_recent_dashboard_items(8)

        self.write({
            "code": 0,
            "data": {
                "stats": stats,
                "source_distribution": source_dist,
                "source_geo": source_geo,
                "trend": trend,
                "keywords": keywords,
                "recent_items": recent_items,
            }
        })
