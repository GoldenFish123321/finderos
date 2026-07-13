"""
home.py — 前台首页控制器

普通用户登录后进入的前台首页。
"""

import tornado.web

from app.controllers.base import BaseHandler
from app.models.user import UserRepository
from app.models.role import RoleRepository
from app.models.function import FunctionRepository


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
        self.render(
            "admin/index.html",
            title="瞭望与问数系统 — 首页",
            username=self.current_user,
            user_count=user_count,
            role_count=role_count,
            func_count=func_count,
        )
