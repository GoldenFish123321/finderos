"""
admin_user.py — 用户管理控制器

系统管理员管理所有用户（新增/编辑/删除/禁用/搜索/分页）。
"""

import tornado.web
from app.controllers.admin_base import AdminBaseHandler
from app.models.user import UserRepository
from app.models.role import RoleRepository
from app.utils.security import write_audit_log

# 密码修改速率限制（用户维度）
_pwd_change_attempts: dict[str, list[float]] = {}
_PWD_CHANGE_MAX = 5
_PWD_CHANGE_WINDOW = 300  # 5分钟


class UserListHandler(AdminBaseHandler):
    """用户列表页"""

    @tornado.web.authenticated
    def get(self):
        page = int(self.get_query_argument("page", 1))
        keyword = self.get_query_argument("keyword", "").strip()
        rows, total = UserRepository.get_all(page=page, page_size=20, keyword=keyword)
        total_pages = max(1, (total + 20 - 1) // 20)

        self.render(
            "admin/user_list.html",
            title="用户管理 — 瞭望与问数系统",
            username=self.current_user,
            users=rows,
            page=page,
            total=total,
            total_pages=total_pages,
            keyword=keyword,
            xsrf_token=self.xsrf_token.decode() if isinstance(self.xsrf_token, bytes) else self.xsrf_token,
        )


class UserFormHandler(AdminBaseHandler):
    """用户新增/编辑表单页"""

    @tornado.web.authenticated
    def get(self):
        user_id = self.get_query_argument("id", None)
        user = None
        if user_id:
            try:
                user = UserRepository.get_user_by_id(int(user_id))
            except (ValueError, TypeError):
                self.write('<script>alert("无效的用户ID");window.history.back();</script>')
                return
            if not user:
                self.write('<script>alert("用户不存在");window.history.back();</script>')
                return

        roles = RoleRepository.get_all(page=1, page_size=100)[0]

        self.render(
            "admin/user_form.html",
            title="编辑用户" if user else "新增用户",
            username=self.current_user,
            user=user,
            roles=roles,
        )

    @tornado.web.authenticated
    def post(self):
        user_id = self.get_body_argument("id", None)
        username = self.get_body_argument("username", "").strip()
        password = self.get_body_argument("password", "").strip()
        role_id_str = self.get_body_argument("role_id", "").strip()

        role_id = int(role_id_str) if role_id_str else None

        if user_id:  # 编辑
            user_id = int(user_id)
            existing = UserRepository.get_user_by_id(user_id)
            if not existing:
                self.write('<script>alert("用户不存在");window.history.back();</script>')
                return
            # 如果未提供用户名，保留原有用户名
            update_username = username if username else existing["username"]
            ok = UserRepository.update_user(user_id, update_username, password, role_id)
            if ok:
                self.redirect("/admin/user?msg=更新成功")
            else:
                self.write('<script>alert("更新失败，用户名可能重复");window.history.back();</script>')
        else:  # 新增
            if not username or not password:
                self.write('<script>alert("用户名和密码不能为空");window.history.back();</script>')
                return
            ok = UserRepository.create_user(username, password, role_id)
            if ok:
                self.redirect("/admin/user?msg=创建成功")
            else:
                self.write('<script>alert("用户名已存在");window.history.back();</script>')


class UserDeleteHandler(AdminBaseHandler):
    """删除用户"""

    @tornado.web.authenticated
    def post(self):
        user_id = int(self.get_body_argument("id", 0))
        user = UserRepository.get_user_by_id(user_id)
        if not user:
            self.write('<script>alert("用户不存在");window.history.back();</script>')
            return
        if user["username"] == "admin":
            self.write('<script>alert("超级管理员 admin 不可删除");window.history.back();</script>')
            return
        # 禁止管理员删除自己
        if user["username"] == self.current_user:
            self.write('<script>alert("不能删除自己的账号");window.history.back();</script>')
            return
        UserRepository.delete_user(user_id)
        self.redirect("/admin/user?msg=已删除")


class UserToggleHandler(AdminBaseHandler):
    """启用/禁用用户"""

    @tornado.web.authenticated
    def post(self):
        user_id = int(self.get_body_argument("id", 0))
        user = UserRepository.get_user_by_id(user_id)
        if not user:
            self.write('<script>alert("用户不存在");window.history.back();</script>')
            return
        # 禁止管理员禁用自己
        if user["username"] == self.current_user:
            self.write('<script>alert("不能禁用自己的账号");window.history.back();</script>')
            return
        if user["username"] == "admin":
            self.write('<script>alert("超级管理员 admin 不可被禁用");window.history.back();</script>')
            return
        status = UserRepository.toggle_enabled(user_id)
        if status == -1:
            self.write('<script>alert("禁用失败");window.history.back();</script>')
        else:
            self.redirect(f"/admin/user?msg={'已启用' if status == 1 else '已禁用'}")


class UserBatchDeleteHandler(AdminBaseHandler):
    """批量删除用户（借鉴冯凯乐项目的批量操作设计）"""

    @tornado.web.authenticated
    def post(self):
        ids_str = self.get_body_argument("ids", "")
        if not ids_str:
            self.set_header("Content-Type", "application/json")
            self.write({"code": 1, "msg": "请选择要删除的用户"})
            return
        try:
            ids = [int(x) for x in ids_str.split(",") if x.strip()]
            # 过滤掉自己的 ID
            current_user = UserRepository.get_user_by_username(self.current_user)
            if current_user:
                ids = [uid for uid in ids if uid != current_user["id"]]
            count, skipped_admin = UserRepository.batch_delete(ids)
            msg = f"成功删除 {count} 个用户"
            if skipped_admin > 0:
                msg += f"（跳过 {skipped_admin} 个受保护的管理员账号）"
            write_audit_log(
                action="USER_BATCH_DELETE",
                username=self.current_user,
                target=f"users:{','.join(str(x) for x in ids[:10])}",
                detail=f"deleted={count}, skipped_admin={skipped_admin}",
                client_ip=self.request.remote_ip or "",
            )
            self.set_header("Content-Type", "application/json")
            self.write({"code": 0, "msg": msg})
        except (ValueError, TypeError):
            self.set_header("Content-Type", "application/json")
            self.write({"code": 1, "msg": "参数格式错误"})


class UserBatchToggleHandler(AdminBaseHandler):
    """批量启用/禁用用户（借鉴冯凯乐项目的批量操作设计）"""

    @tornado.web.authenticated
    def post(self):
        ids_str = self.get_body_argument("ids", "")
        enable_str = self.get_body_argument("enable", "1")
        if not ids_str:
            self.set_header("Content-Type", "application/json")
            self.write({"code": 1, "msg": "请选择要操作的用户"})
            return
        try:
            ids = [int(x) for x in ids_str.split(",") if x.strip()]
            # 过滤掉自己的 ID（禁用时）
            if enable_str != "1":
                current_user = UserRepository.get_user_by_username(self.current_user)
                if current_user:
                    ids = [uid for uid in ids if uid != current_user["id"]]
            enable = enable_str == "1"
            count, skipped_admin = UserRepository.batch_toggle(ids, enable)
            action = "启用" if enable else "禁用"
            msg = f"成功{action} {count} 个用户"
            if skipped_admin > 0:
                msg += f"（跳过 {skipped_admin} 个受保护的管理员账号）"
            write_audit_log(
                action="USER_BATCH_TOGGLE",
                username=self.current_user,
                target=f"users:{','.join(str(x) for x in ids[:10])}",
                detail=f"action={action}, count={count}, skipped_admin={skipped_admin}",
                client_ip=self.request.remote_ip or "",
            )
            self.set_header("Content-Type", "application/json")
            self.write({"code": 0, "msg": msg})
        except (ValueError, TypeError):
            self.set_header("Content-Type", "application/json")
            self.write({"code": 1, "msg": "参数格式错误"})


class ChangePasswordHandler(AdminBaseHandler):
    """用户自助修改密码"""

    @tornado.web.authenticated
    def get(self):
        self.render(
            "admin/change_password.html",
            title="修改密码 — 瞭望与问数系统",
            username=self.current_user,
        )

    @tornado.web.authenticated
    def post(self):
        import time
        old_password = self.get_body_argument("old_password", "").strip()
        new_password = self.get_body_argument("new_password", "").strip()
        confirm_password = self.get_body_argument("confirm_password", "").strip()

        # 速率限制检查
        rate_key = f"pwd:{self.current_user}"
        now = time.time()
        attempts = _pwd_change_attempts.get(rate_key, [])
        attempts = [t for t in attempts if now - t < _PWD_CHANGE_WINDOW]
        if len(attempts) >= _PWD_CHANGE_MAX:
            self.write('<script>alert("操作过于频繁，请5分钟后再试");window.history.back();</script>')
            return

        if not old_password or not new_password:
            self.write('<script>alert("请填写所有字段");window.history.back();</script>')
            return
        if new_password != confirm_password:
            self.write('<script>alert("两次输入的新密码不一致");window.history.back();</script>')
            return
        if len(new_password) < 6:
            self.write('<script>alert("新密码长度不能少于6个字符");window.history.back();</script>')
            return

        user = UserRepository.get_user_by_username(self.current_user)
        if not user:
            self.write('<script>alert("用户不存在");window.history.back();</script>')
            return

        ok, msg = UserRepository.update_password(user["id"], old_password, new_password)
        if ok:
            # 成功后清除速率记录
            _pwd_change_attempts.pop(rate_key, None)
            write_audit_log(
                action="CHANGE_PASSWORD",
                username=self.current_user,
                target=f"user:{user['id']}",
                detail="密码修改成功",
                client_ip=self.request.remote_ip or "",
            )
            self.write(f'<script>alert("{msg}，请重新登录");location.href="/logout";</script>')
        else:
            # 记录失败尝试
            attempts.append(now)
            _pwd_change_attempts[rate_key] = attempts
            write_audit_log(
                action="CHANGE_PASSWORD_FAILED",
                username=self.current_user,
                target=f"user:{user['id']}",
                detail=f"失败原因: {msg}",
                client_ip=self.request.remote_ip or "",
            )
            self.write(f'<script>alert("{msg}");window.history.back();</script>')
