"""
admin_home.py — 管理后台 Dashboard 控制器

后台首页展示概览数据和统计卡片。
"""
import tornado.web
from app.controllers.admin_base import AdminBaseHandler
from app.models.user import UserRepository
from app.models.role import RoleRepository
from app.models.function import FunctionRepository
from app.models.watch_source import WatchSourceRepository
from app.models.watch_result import WatchResultRepository
from app.models.ai_model import AiModelRepository


class AdminIndexHandler(AdminBaseHandler):
    """管理后台 Dashboard"""

    @tornado.web.authenticated
    def get(self):
        user_count = UserRepository.get_user_count()
        role_count = RoleRepository.get_count()
        func_count = FunctionRepository.get_count()
        source_count = WatchSourceRepository.get_count()
        result_count = WatchResultRepository.get_count()
        model_count = AiModelRepository.get_count()
        result_stats = WatchResultRepository.get_stats()
        model_stats = AiModelRepository.get_stats()

        self.render(
            "admin/index.html",
            title="管理后台 — 瞭望与问数系统",
            username=self.current_user,
            user_count=user_count,
            role_count=role_count,
            func_count=func_count,
            source_count=source_count,
            result_count=result_count,
            model_count=model_count,
            result_stats=result_stats,
            model_stats=model_stats,
        )
