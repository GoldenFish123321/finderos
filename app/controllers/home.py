"""
home.py — 前台首页控制器

登录后默认进入前台智能问数页。
"""

import tornado.web

from app.controllers.base import BaseHandler


class IndexHandler(BaseHandler):
    """
    前台首页处理器。
    登录后的默认落点始终是 /chat；后台入口由页面链接进入。
    """

    @tornado.web.authenticated
    def get(self):
        self.redirect("/chat")
