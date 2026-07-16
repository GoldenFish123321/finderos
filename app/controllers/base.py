"""
base.py — Controller 公共基础类 (BaseHandler)

在 Tornado 中：
- 每个 URL 对应一个 RequestHandler（可以理解成是一个 Controller）
- RequestHandler 中提供常用的请求和响应逻辑，同时支持 get/post/put/delete......
- 本 BaseHandler 主要是提供统一的登录态获得逻辑，供其他 Handler 继承使用。
"""

import tornado.web
from app.config.settings import settings
from app.models.user import UserRepository


class BaseHandler(tornado.web.RequestHandler):
    """
    公共基础 Handler，提供用户认证相关方法。
    所有需要登录验证的 Handler 都应继承此类。
    """

    def get_template_namespace(self):
        """注入全局模板变量，包括统一版本号和系统设置。"""
        namespace = super().get_template_namespace()
        namespace["app_version"] = settings.VERSION
        namespace["settings"] = settings
        return namespace

    def set_default_headers(self):
        """为所有响应设置 OWASP 推荐的安全响应头。"""
        for header_name, header_value in settings.SECURITY_HEADERS.items():
            self.set_header(header_name, header_value)

    def get_current_user(self) -> str | None:
        """
        从安全 Cookie 中获取当前登录用户名。
        Tornado 会自动将返回值赋值给 self.current_user 属性。
        返回 None 表示未登录。
        """
        username = self.get_secure_cookie(
            "username", max_age_days=settings.SESSION_EXPIRE_HOURS / 24
        )
        if not username:
            return None
        try:
            username_text = username.decode("utf-8")
        except UnicodeDecodeError:
            self.clear_cookie("username")
            return None
        user = UserRepository.get_user_by_username(username_text)
        if not user or user["is_enabled"] == 0:
            self.clear_cookie("username")
            return None
        return username_text

    def write_error(self, status_code: int, **kwargs) -> None:
        """自定义错误页面。"""
        if status_code == 403:
            self.write("<h2>403 禁止访问</h2><p>请先登录后再访问。</p>")
        elif status_code == 404:
            self.write("<h2>404 页面未找到</h2>")
        else:
            if settings.DEBUG:
                self.write(f"<h2>{status_code} {self._reason}</h2>")
            else:
                self.write(f"<h2>{status_code} 服务器错误</h2>")
