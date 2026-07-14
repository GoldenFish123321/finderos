"""
admin_base.py — 管理后台公共基类

提供管理后台通用的权限校验（AdminBaseHandler）。
管理员需要拥有"系统管理员"角色才能访问管理页面。
"""

import tornado.web
from app.controllers.base import BaseHandler
from app.models.user import UserRepository
from app.utils.security import write_audit_log


class AdminBaseHandler(BaseHandler):
    """
    管理后台基础 Handler。
    所有管理页面继承此类，自动校验管理员权限。
    """

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

        # 检查用户角色是否有后台功能权限
        role = UserRepository.get_user_role(self.current_user)
        if not role:
            write_audit_log(
                action="ACCESS_DENIED_NO_ROLE",
                username=self.current_user,
                target=self.request.path,
                detail="无角色用户尝试访问管理后台",
                client_ip=self.request.remote_ip or "",
            )
            self.set_status(403)
            self.write("""
            <div style="text-align:center;padding:60px 20px;">
                <i class="layui-icon layui-icon-close-fill" style="font-size:60px;color:#FF5722;"></i>
                <h2 style="margin-top:20px;">403 权限不足</h2>
                <p style="color:#999;margin-top:10px;">您没有分配角色，请联系系统管理员。</p>
                <a href="/logout" style="margin-top:20px;display:inline-block;">返回登录</a>
            </div>
            """)
            self.finish()
            return

        # 检查角色是否有关联的功能（系统管理员或自定义管理员角色）
        funcs = UserRepository.get_user_functions(self.current_user)
        if not funcs:
            write_audit_log(
                action="ACCESS_DENIED_NO_FUNCTIONS",
                username=self.current_user,
                target=self.request.path,
                detail=f"角色'{role['name']}'无功能权限访问管理后台",
                client_ip=self.request.remote_ip or "",
            )
            self.set_status(403)
            self.write("""
            <div style="text-align:center;padding:60px 20px;">
                <i class="layui-icon layui-icon-close-fill" style="font-size:60px;color:#FF5722;"></i>
                <h2 style="margin-top:20px;">403 权限不足</h2>
                <p style="color:#999;margin-top:10px;">您的角色没有分配任何功能权限，请联系系统管理员。</p>
                <a href="/logout" style="margin-top:20px;display:inline-block;">返回登录</a>
            </div>
            """)
            self.finish()
            return
