"""
home.py — 前台首页控制器

普通用户登录后进入的前台首页。
"""

import tornado.web

from app.controllers.base import BaseHandler
from app.models.user import UserRepository
from app.models.role import RoleRepository
from app.models.function import FunctionRepository
from app.models.watch_source import WatchSourceRepository
from app.models.watch_result import WatchResultRepository
from app.models.ai_model import AiModelRepository


class IndexHandler(BaseHandler):
    """
    前台首页处理器。
    使用 @authenticated 装饰器确保只有登录用户可访问。
    """

    @tornado.web.authenticated
    def get(self):
        user_count = UserRepository.get_user_count()
        role_count = RoleRepository.get_count()
        func_count = FunctionRepository.get_count()
        source_count = WatchSourceRepository.get_count()
        result_count = WatchResultRepository.get_count()
        result_stats = WatchResultRepository.get_stats()
        model_count = AiModelRepository.get_count()
        model_stats = AiModelRepository.get_stats()
        self.render(
            "admin/index.html",
            title="瞭望与问数系统 — 首页",
            username=self.current_user,
            user_count=user_count,
            role_count=role_count,
            func_count=func_count,
            source_count=source_count,
            result_count=result_count,
            result_stats=result_stats,
            model_count=model_count,
            model_stats=model_stats,
        )
