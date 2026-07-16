"""
admin_base.py — 管理后台公共基类

提供管理后台通用的权限校验（AdminBaseHandler）。
后台访问基于 RBAC 功能路由授权：用户角色必须拥有当前路由对应的功能节点。
"""

from html import escape

import tornado.web
from app.controllers.base import BaseHandler
from app.config.settings import settings
from app.models.function import FunctionRepository
from app.models.user import UserRepository
from app.utils.security import write_audit_log


ADMIN_ROUTE_PERMISSION_ALIASES = {
    # JSON API / action endpoints that do not share the visible menu prefix.
    "/admin/api/model/list": "/admin/model",
    "/admin/api/interface/list": "/admin/interface",
    "/admin/api/employee/list": "/admin/employee",
    "/admin/api/dashboard": "/admin/dashboard",
    "/admin/api/sentiment": "/admin/sentiment",
    "/admin/api/sentiment/scan": "/admin/sentiment",
    "/admin/api/sentiment/detail": "/admin/sentiment",
    "/admin/api/sentiment/resolve": "/admin/sentiment",
    "/admin/api/sentiment/analyze": "/admin/sentiment",
    "/admin/mcp/reload": "/admin/mcp/tool",
}

ADMIN_ALWAYS_ALLOWED_PATHS = {
    # Any authenticated and enabled user can change their own password.
    "/admin/user/change-password",
}


class AdminBaseHandler(BaseHandler):
    """
    管理后台基础 Handler。
    所有管理页面继承此类，自动校验登录态、账号状态和功能路由权限。
    """

    def get_template_namespace(self):
        """Inject admin permission helpers and settings into templates."""
        namespace = super().get_template_namespace()
        namespace["admin_can"] = self.has_admin_route_permission
        namespace["settings"] = settings
        return namespace

    def prepare(self):
        """请求预处理：校验管理员权限。"""
        super().prepare()
        if not self.current_user:
            self.redirect(self.settings.get("login_url", "/"))
            return

        # 检查用户是否被禁用
        user = UserRepository.get_user_by_username(self.current_user)
        if not user or user["is_enabled"] == 0:
            write_audit_log(
                action="ACCESS_DENIED_DISABLED",
                username=self.current_user or "",
                target=self.request.path,
                detail="禁用用户尝试访问管理后台",
                client_ip=self.request.remote_ip or "",
            )
            self.clear_cookie("username")
            self.redirect(self.settings.get("login_url", "/"))
            return

        # 检查用户角色是否存在
        role = UserRepository.get_user_role(self.current_user)
        if not role:
            self._deny(
                action="ACCESS_DENIED_NO_ROLE",
                detail="无角色用户尝试访问管理后台",
                message="您没有分配角色，请联系系统管理员。",
                logout_link=True,
            )
            return

        allowed_routes = set(UserRepository.get_user_function_routes(self.current_user))
        self._admin_allowed_routes = allowed_routes
        required_route = self._resolve_required_route(self.request.path)

        # 自助改密等显式白名单路由：只要求登录且账号启用。
        if required_route is None:
            return

        # 检查角色是否有关联的功能（系统管理员或自定义管理员角色）
        funcs = UserRepository.get_user_functions(self.current_user)
        if not funcs:
            self._deny(
                action="ACCESS_DENIED_NO_FUNCTIONS",
                detail=f"角色'{role['name']}'无功能权限访问管理后台",
                message="您的角色没有分配任何功能权限，请联系系统管理员。",
                logout_link=True,
            )
            return

        # 路由级权限：拥有后台任意功能不再等于拥有全部后台路由。
        if required_route not in allowed_routes:
            self._deny(
                action="ACCESS_DENIED_FUNCTION",
                detail=f"缺少功能权限: {required_route}",
                message=f"您没有访问该功能的权限：{escape(required_route)}",
                logout_link=False,
            )
            return

    def has_admin_route_permission(self, route_path: str) -> bool:
        """Return whether current user owns the given admin function route."""
        if route_path in ADMIN_ALWAYS_ALLOWED_PATHS:
            return True
        allowed_routes = getattr(self, "_admin_allowed_routes", None)
        if allowed_routes is None:
            if not self.current_user:
                return False
            allowed_routes = set(UserRepository.get_user_function_routes(self.current_user))
            self._admin_allowed_routes = allowed_routes
        return route_path in allowed_routes

    def _is_route_authorized(self, function_ids: list[int]) -> bool:
        """Compatibility helper for checking action routes by function IDs."""
        path = self.request.path.rstrip("/") or "/"
        for api_prefix, owner in ADMIN_ROUTE_PERMISSION_ALIASES.items():
            prefix = api_prefix.rstrip("/") or "/"
            if path == prefix or path.startswith(prefix + "/"):
                path = owner + path[len(prefix):]
                break
        if path == "/admin/user/change-password":
            return bool(function_ids)
        if not function_ids:
            return False

        from app.models.db import get_db
        placeholders = ",".join("?" for _ in function_ids)
        with get_db() as conn:
            rows = conn.execute(
                f"SELECT route_path FROM functions WHERE id IN ({placeholders}) "
                "AND is_enabled = 1 AND route_path != ''",
                function_ids,
            ).fetchall()
        routes = {row["route_path"].rstrip("/") or "/" for row in rows}
        if path == "/admin":
            return "/admin" in routes
        return any(
            route != "/admin" and (path == route or path.startswith(route + "/"))
            for route in routes
        )

    def _resolve_required_route(self, path: str) -> str | None:
        """Resolve the function route required by the current request path.

        The functions table stores visible menu routes such as ``/admin/model``.
        Child actions like ``/admin/model/add`` inherit that permission. When
        multiple function routes match, the longest route wins so more specific
        permissions override broader module permissions.
        """
        clean_path = (path or "").split("?", 1)[0].rstrip("/") or "/"
        if clean_path in ADMIN_ALWAYS_ALLOWED_PATHS:
            return None

        for alias_path, required_route in ADMIN_ROUTE_PERMISSION_ALIASES.items():
            alias_path = alias_path.rstrip("/") or "/"
            if clean_path == alias_path or clean_path.startswith(alias_path + "/"):
                return required_route

        for route in FunctionRepository.get_route_paths(enabled_only=False):
            route = route.rstrip("/") or "/"
            if route == "/admin":
                if clean_path == "/admin":
                    return route
                continue
            if clean_path == route or clean_path.startswith(route + "/"):
                return route

        # Unknown admin endpoints are denied by default unless explicitly added
        # to functions or ADMIN_ROUTE_PERMISSION_ALIASES.
        return clean_path

    def _deny(self, action: str, detail: str, message: str, logout_link: bool = False):
        """Write audit log and render a compact 403 response."""
        write_audit_log(
            action=action,
            username=self.current_user or "",
            target=self.request.path,
            detail=detail,
            client_ip=self.request.remote_ip or "",
        )
        self.set_status(403)
        if logout_link:
            href = "/logout"
            text = "返回登录"
        else:
            allowed_routes = getattr(self, "_admin_allowed_routes", set()) or set()
            href = "/admin" if "/admin" in allowed_routes else next(
                (r for r in sorted(allowed_routes) if r.startswith("/admin")), "/chat"
            )
            text = "返回可用功能" if href != "/chat" else "返回前台"
        self.render("admin/403.html", message=message, link=href, link_text=text)
