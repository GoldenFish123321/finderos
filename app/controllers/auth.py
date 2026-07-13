"""
auth.py — 认证相关控制器

处理用户登录、登出逻辑。
登录后根据角色跳转：系统管理员 → 管理后台，普通用户 → 用户前台。
"""

import time
import tornado.web

from app.config.settings import settings
from app.controllers.base import BaseHandler
from app.models.user import UserRepository
from app.utils.security import write_audit_log

# ========== 登录失败限速（内存级） ==========
# 结构: {(ip, username): (failure_count, first_failure_timestamp)}
_login_failures: dict = {}


def _check_rate_limit(ip: str, username: str) -> tuple[bool, str]:
    """
    检查登录频率限制。
    返回 (允许登录, 错误消息)。
    同一 IP+用户名组合在锁定期窗口内最多失败 N 次。
    """
    now = time.time()
    key = (ip, username)

    # 清理过期条目，防止内存泄漏
    expired_keys = [k for k, (c, ts) in _login_failures.items()
                    if now - ts > settings.LOGIN_LOCKOUT_SECONDS]
    for k in expired_keys:
        del _login_failures[k]

    count, first_ts = _login_failures.get(key, (0, now))

    # 窗口过期，重置
    if now - first_ts > settings.LOGIN_LOCKOUT_SECONDS:
        _login_failures.pop(key, None)
        return True, ""

    if count >= settings.LOGIN_MAX_FAILURES:
        remaining = int(settings.LOGIN_LOCKOUT_SECONDS - (now - first_ts))
        return False, f"登录失败次数过多，请 {max(remaining, 1)} 秒后再试"

    return True, ""


def _record_failure(ip: str, username: str):
    """记录一次登录失败。"""
    now = time.time()
    key = (ip, username)
    count, first_ts = _login_failures.get(key, (0, now))
    # 窗口过期，重置计数
    if now - first_ts > settings.LOGIN_LOCKOUT_SECONDS:
        _login_failures[key] = (1, now)
    else:
        _login_failures[key] = (count + 1, first_ts)


def _clear_failures(ip: str, username: str):
    """登录成功后清除失败记录。"""
    _login_failures.pop((ip, username), None)


class LoginHandler(BaseHandler):
    """登录处理器"""

    def get(self):
        # 已登录用户直接跳转
        if self.current_user:
            return self._redirect_by_role(self.current_user)
        self.render("login.html", title="瞭望与问数系统 — 用户登录", error=None)

    def post(self):
        # 已登录用户直接跳转
        if self.current_user:
            return self._redirect_by_role(self.current_user)

        username = self.get_body_argument("username", "").strip()
        password = self.get_body_argument("password", "")

        # 参数校验
        if not username or not password:
            return self.render(
                "login.html",
                title="瞭望与问数系统 — 用户登录",
                error="用户名和密码不能为空",
            )

        # 频率限制检查
        client_ip = self.request.remote_ip or "0.0.0.0"
        allowed, rate_limit_error = _check_rate_limit(client_ip, username)
        if not allowed:
            write_audit_log("LOGIN_BLOCKED", username, "rate_limit", rate_limit_error, client_ip)
            return self.render(
                "login.html",
                title="瞭望与问数系统 — 用户登录",
                error=rate_limit_error,
            )

        # 验证用户
        if not UserRepository.verify_user(username, password):
            _record_failure(client_ip, username)
            write_audit_log("LOGIN_FAIL", username, "password", "密码错误", client_ip)
            return self.render(
                "login.html",
                title="瞭望与问数系统 — 用户登录",
                error="用户名或密码错误",
            )

        # 登录成功：清除限速记录，设置安全 Cookie
        _clear_failures(client_ip, username)
        self.set_secure_cookie("username", username)
        write_audit_log("LOGIN_SUCCESS", username, "", "登录成功", client_ip)
        self._redirect_by_role(username)

    def _redirect_by_role(self, username: str):
        """根据用户角色跳转到对应页面。"""
        role = UserRepository.get_user_role(username)
        if not role:
            self.redirect("/index")
            return

        # 普通用户只能去前台
        if role["name"] == "普通用户":
            self.redirect("/index")
            return

        # 系统管理员或有功能权限的角色的用户去后台
        funcs = UserRepository.get_user_functions(username)
        if funcs:
            self.redirect("/admin")
        else:
            self.redirect("/index")


class LogoutHandler(BaseHandler):
    """登出处理器"""

    def get(self):
        self.clear_cookie("username")
        self.redirect("/")


class RegisterHandler(BaseHandler):
    """用户注册处理器（前台自助注册）"""

    def get(self):
        if self.current_user:
            return self.redirect("/index")
        self.render("register.html", title="用户注册 — 瞭望与问数系统", error=None)

    def post(self):
        if self.current_user:
            return self.redirect("/index")

        username = self.get_body_argument("username", "").strip()
        password = self.get_body_argument("password", "").strip()
        password_confirm = self.get_body_argument("password_confirm", "").strip()

        # 参数校验
        if not username or not password:
            return self.render(
                "register.html",
                title="用户注册 — 瞭望与问数系统",
                error="用户名和密码不能为空",
            )
        if len(username) < 2:
            return self.render(
                "register.html",
                title="用户注册 — 瞭望与问数系统",
                error="用户名至少需要2个字符",
            )
        if len(password) < 6:
            return self.render(
                "register.html",
                title="用户注册 — 瞭望与问数系统",
                error="密码至少需要6个字符",
            )
        if password != password_confirm:
            return self.render(
                "register.html",
                title="用户注册 — 瞭望与问数系统",
                error="两次密码输入不一致",
            )

        # 检查用户名是否已存在
        if UserRepository.get_user_by_username(username):
            return self.render(
                "register.html",
                title="用户注册 — 瞭望与问数系统",
                error="该用户名已被注册",
            )

        # 创建用户（默认角色：普通用户 id=2）
        success = UserRepository.create_user(username, password, role_id=2)
        if not success:
            return self.render(
                "register.html",
                title="用户注册 — 瞭望与问数系统",
                error="注册失败，请稍后重试",
            )

        client_ip = self.request.remote_ip or "0.0.0.0"
        write_audit_log("REGISTER", username, "", "用户自助注册成功", client_ip)

        # 注册成功后自动登录
        self.set_secure_cookie("username", username)
        self.redirect("/index?msg=注册成功，欢迎使用瞭望与问数系统！")
