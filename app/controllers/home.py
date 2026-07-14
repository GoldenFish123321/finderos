"""
home.py — 前台首页控制器

普通用户登录后进入的前台首页。
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
        # 有管理权限的用户直接跳转管理后台（根据功能权限判断，避免硬编码角色名）
        funcs = UserRepository.get_user_functions(self.current_user)
        if funcs:
            self.redirect("/admin")
            return

        # 普通用户直接跳转到智能问数对话页面
        self.redirect("/chat")
