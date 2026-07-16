"""
auth.py — 认证相关控制器

处理用户登录、登出逻辑。
登录成功后统一进入前台智能问数页；后台入口由前台/导航中的链接进入。
"""

import time
import threading
import tornado.web

from app.config.settings import settings
from app.controllers.base import BaseHandler
from app.models.user import UserRepository
from app.models.role import RoleRepository
from app.utils.security import validate_password_strength, write_audit_log


class LoginRateLimiter:
    """登录频率限制器（内存级，支持独立作用域）。

    参考 OWASP 认证防护最佳实践，按 IP+用户名 组合进行失败计数。
    超过阈值后锁定期内禁止该组合继续尝试登录。

    使用示例:
        limiter = LoginRateLimiter(scope="admin")
        allowed, msg = limiter.check(ip, username)
        if not allowed: ...
        limiter.record_failure(ip, username)
        limiter.clear(ip, username)
    """

    def __init__(self, scope: str = "default"):
        self._scope = scope
        self._failures: dict = {}  # {(ip, username): (count, first_ts)}
        self._lock = threading.RLock()

    def _cleanup_expired(self, now: float):
        """清理所有过期的失败记录，防止内存泄漏。"""
        lockout = settings.LOGIN_LOCKOUT_SECONDS
        expired = [k for k, (_, ts) in self._failures.items() if now - ts > lockout]
        for k in expired:
            del self._failures[k]

    def check(self, ip: str, username: str) -> tuple[bool, str]:
        """检查是否允许登录。返回 (允许, 错误消息)。"""
        now = time.time()
        with self._lock:
            self._cleanup_expired(now)
            key = (ip, username)
            count, first_ts = self._failures.get(key, (0, now))

            if now - first_ts > settings.LOGIN_LOCKOUT_SECONDS:
                self._failures.pop(key, None)
                return True, ""

            if count >= settings.LOGIN_MAX_FAILURES:
                remaining = int(settings.LOGIN_LOCKOUT_SECONDS - (now - first_ts))
                return False, f"操作过于频繁，请 {max(remaining, 1)} 秒后再试"

            return True, ""

    def record_failure(self, ip: str, username: str):
        """记录一次登录失败。"""
        now = time.time()
        with self._lock:
            self._cleanup_expired(now)
            key = (ip, username)
            count, first_ts = self._failures.get(key, (0, now))
            if now - first_ts > settings.LOGIN_LOCKOUT_SECONDS:
                self._failures[key] = (1, now)
            else:
                self._failures[key] = (count + 1, first_ts)

    def clear(self, ip: str, username: str):
        """登录成功后清除失败记录。"""
        with self._lock:
            self._failures.pop((ip, username), None)


# 全局登录限速器实例
login_limiter = LoginRateLimiter(scope="global")
register_limiter = LoginRateLimiter(scope="register")


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
        password = self.get_body_argument("password", "").strip()

        # 参数校验
        if not username or not password:
            return self.render(
                "login.html",
                title="瞭望与问数系统 — 用户登录",
                error="用户名和密码不能为空",
            )

        # 频率限制检查
        client_ip = self.request.remote_ip or "0.0.0.0"
        allowed, rate_limit_error = login_limiter.check(client_ip, username)
        if not allowed:
            write_audit_log("LOGIN_BLOCKED", username, "rate_limit", rate_limit_error, client_ip)
            return self.render(
                "login.html",
                title="瞭望与问数系统 — 用户登录",
                error=rate_limit_error,
            )

        # 验证用户
        if not UserRepository.verify_user(username, password):
            login_limiter.record_failure(client_ip, username)
            write_audit_log("LOGIN_FAIL", username, "password", "密码错误", client_ip)
            return self.render(
                "login.html",
                title="瞭望与问数系统 — 用户登录",
                error="用户名或密码错误",
            )

        # 登录成功：清除限速记录，设置安全 Cookie（含 Secure/SameSite 属性）
        login_limiter.clear(client_ip, username)
        is_https = self.request.protocol == "https"
        self.set_secure_cookie(
            "username", username,
            httponly=True,
            samesite="Lax",
            secure=is_https,
            expires_days=settings.SESSION_EXPIRE_HOURS / 24,
        )
        write_audit_log("LOGIN_SUCCESS", username, "", "登录成功", client_ip)
        self._redirect_by_role(username)

    def _redirect_by_role(self, username: str):
        """登录后统一进入前台问数页，避免普通用户被带到模型配置页。"""
        self.redirect("/chat")


class LogoutHandler(BaseHandler):
    """登出处理器"""

    def get(self):
        write_audit_log(
            action="LOGOUT",
            username=self.current_user or "unknown",
            target="session",
            detail="用户主动登出",
            client_ip=self.request.remote_ip or "",
        )
        self.clear_cookie("username")
        self.redirect("/")


class RegisterHandler(BaseHandler):
    """用户注册处理器（前台自助注册）"""

    def get(self):
        if not settings.REGISTRATION_ENABLED:
            self.set_status(403)
            self.write("用户注册当前已关闭")
            return
        if self.current_user:
            return self.redirect("/chat")

        self.render("register.html", title="用户注册 - 瞭望与问数系统", error=None)

    def post(self):
        if not settings.REGISTRATION_ENABLED:
            self.set_status(403)
            self.write("用户注册当前已关闭")
            return
        if self.current_user:
            return self.redirect("/chat")

        client_ip = self.request.remote_ip or "0.0.0.0"
        allowed, rate_limit_error = register_limiter.check(client_ip, "*")
        if not allowed:
            write_audit_log("REGISTER_BLOCKED", "", "rate_limit", rate_limit_error, client_ip)
            return self.render("register.html", title="用户注册", error=rate_limit_error)
        register_limiter.record_failure(client_ip, "*")

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
        valid, pwd_error = validate_password_strength(password)
        if not valid:
            return self.render(
                "register.html",
                title="用户注册 — 瞭望与问数系统",
                error=pwd_error,
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

        # 创建用户（默认角色：动态查找"普通用户"角色，而非硬编码 role_id）
        default_role = RoleRepository.get_by_name("普通用户")
        role_id = default_role["id"] if default_role else 2
        success = UserRepository.create_user(username, password, role_id=role_id)
        if not success:
            return self.render(
                "register.html",
                title="用户注册 — 瞭望与问数系统",
                error="注册失败，请稍后重试",
            )

        write_audit_log("REGISTER", username, "", "用户自助注册成功", client_ip)

        # 注册成功后自动登录
        is_https = self.request.protocol == "https"
        self.set_secure_cookie(
            "username", username,
            httponly=True,
            samesite="Lax",
            secure=is_https,
            expires_days=settings.SESSION_EXPIRE_HOURS / 24,
        )
        self.redirect("/chat")


class FaceRegisterHandler(BaseHandler):
    """人脸注册 — 保存 128 维特征描述符到用户记录"""

    @tornado.web.authenticated
    def post(self):
        try:
            descriptor_str = self.get_body_argument("descriptor", "")
        except Exception:
            self.write({"code": 1, "msg": "参数错误"})
            return
        if not descriptor_str:
            self.write({"code": 1, "msg": "人脸数据不能为空"})
            return
        import json
        try:
            descriptor = json.loads(descriptor_str)
        except (json.JSONDecodeError, TypeError):
            self.write({"code": 1, "msg": "人脸数据格式错误"})
            return
        if not isinstance(descriptor, list) or len(descriptor) != 128:
            self.write({"code": 1, "msg": "人脸数据维度错误（需要 128 维）"})
            return
        ok = UserRepository.save_face_descriptor(self.current_user, descriptor)
        if ok:
            write_audit_log("FACE_REGISTER", self.current_user, "", "人脸注册成功",
                            self.request.remote_ip or "")
            self.write({"code": 0, "msg": "人脸注册成功"})
        else:
            self.write({"code": 1, "msg": "保存失败"})


class FaceLoginHandler(BaseHandler):
    """人脸登录 — 上传人脸特征，匹配后自动登录"""

    def post(self):
        if self.current_user:
            self.write({"code": 0, "msg": "已登录", "redirect": "/index"})
            return

        client_ip = self.request.remote_ip or "0.0.0.0"
        allowed, rate_limit_error = login_limiter.check(client_ip, "*face*")
        if not allowed:
            self.write({"code": 1, "msg": rate_limit_error})
            return

        try:
            descriptor_str = self.get_body_argument("descriptor", "")
        except Exception:
            self.write({"code": 1, "msg": "参数错误"})
            return
        if not descriptor_str:
            self.write({"code": 1, "msg": "人脸数据不能为空"})
            return

        import json
        try:
            descriptor = json.loads(descriptor_str)
        except (json.JSONDecodeError, TypeError):
            self.write({"code": 1, "msg": "人脸数据格式错误"})
            return
        if not isinstance(descriptor, list) or len(descriptor) != 128:
            self.write({"code": 1, "msg": "人脸数据维度错误（需要 128 维）"})
            return

        username = UserRepository.match_face(descriptor)
        if not username:
            login_limiter.record_failure(client_ip, "*face*")
            write_audit_log("FACE_LOGIN_FAIL", "", "", "人脸匹配失败", client_ip)
            self.write({"code": 1, "msg": "人脸识别失败，请重试或使用密码登录"})
            return

        user = UserRepository.get_user_by_username(username)
        if not user or user.get("is_enabled") == 0:
            self.write({"code": 1, "msg": "账户已被禁用"})
            return

        login_limiter.clear(client_ip, "*face*")
        login_limiter.clear(client_ip, username)
        is_https = self.request.protocol == "https"
        self.set_secure_cookie(
            "username", username,
            httponly=True, samesite="Lax", secure=is_https,
            expires_days=settings.SESSION_EXPIRE_HOURS / 24,
        )
        write_audit_log("FACE_LOGIN_SUCCESS", username, "", "人脸登录成功", client_ip)

        role = UserRepository.get_user_role(username)
        if role:
            routes = [r for r in UserRepository.get_user_function_routes(username)
                      if r.startswith("/admin")]
            redirect = "/admin" if "/admin" in routes else (routes[0] if routes else "/index")
        else:
            redirect = "/index"

        self.write({"code": 0, "msg": "登录成功", "redirect": redirect})
