"""
home.py — 前台首页控制器

无后台功能权限的用户登录后进入前台首页。
"""

import tornado.web

from app.controllers.base import BaseHandler
from app.models.user import UserRepository
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
        # 有管理权限的用户直接跳转后台（根据功能权限判断，避免硬编码角色名）
        routes = [r for r in UserRepository.get_user_function_routes(self.current_user) if r.startswith("/admin")]
        if routes:
            self.redirect("/admin" if "/admin" in routes else routes[0])
            return

        # 无后台功能权限的用户直接跳转到智能问数对话页面
        self.redirect("/chat")
