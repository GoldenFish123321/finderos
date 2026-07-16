"""
admin_user.py — 用户管理控制器

系统管理员管理所有用户（新增/编辑/删除/禁用/搜索/分页）。
"""

import tornado.web
import threading
from tornado.escape import xhtml_escape
from app.controllers.admin_base import AdminBaseHandler
from app.models.user import UserRepository
from app.models.role import RoleRepository
from app.utils.security import write_audit_log

# 密码修改速率限制（用户维度）
_pwd_change_attempts: dict[str, list[float]] = {}
_pwd_change_lock = threading.RLock()
_PWD_CHANGE_MAX = 5
_PWD_CHANGE_WINDOW = 300  # 5分钟


def _reserve_password_attempt(rate_key: str, now: float) -> bool:
    """Atomically check the password-change limit and reserve this attempt."""
    with _pwd_change_lock:
        attempts = [t for t in _pwd_change_attempts.get(rate_key, []) if now - t < _PWD_CHANGE_WINDOW]
        if len(attempts) >= _PWD_CHANGE_MAX:
            _pwd_change_attempts[rate_key] = attempts
            return False
        attempts.append(now)
        _pwd_change_attempts[rate_key] = attempts
        return True


class UserListHandler(AdminBaseHandler):
    """用户列表页"""

    @tornado.web.authenticated
    def get(self):
        try:
            page = int(self.get_query_argument("page", 1))
        except (ValueError, TypeError):
            page = 1
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
            # 禁止管理员修改自己的角色（防止自降权限）
            if existing["username"] == self.current_user:
                if role_id_str and int(role_id_str) != existing["role_id"]:
                    self.write('<script>alert("不能修改自己的角色权限");window.history.back();</script>')
                    return
            # 禁止将 admin 超级管理员降为普通用户
            if existing["username"] == "admin" and role_id_str:
                admin_role = RoleRepository.get_by_name("系统管理员")
                if admin_role and int(role_id_str) != admin_role["id"]:
                    self.write('<script>alert("超级管理员 admin 的角色不可更改");window.history.back();</script>')
                    return
            # 如果未提供用户名/角色，保留原有值（避免静默清空）
            update_username = username if username else existing["username"]
            update_role_id = role_id if role_id_str else existing["role_id"]
            ok = UserRepository.update_user(user_id, update_username, password, update_role_id)
            if ok:
                write_audit_log("USER_UPDATE", self.current_user, f"user:{user_id}", update_username, self.request.remote_ip or "")
                self.redirect("/admin/user?msg=更新成功")
            else:
                self.write('<script>alert("更新失败，用户名可能重复");window.history.back();</script>')
        else:  # 新增
            if not username or not password:
                self.write('<script>alert("用户名和密码不能为空");window.history.back();</script>')
                return
            ok = UserRepository.create_user(username, password, role_id)
            if ok:
                created = UserRepository.get_user_by_username(username)
                write_audit_log("USER_CREATE", self.current_user, f"user:{created['id'] if created else username}", username, self.request.remote_ip or "")
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
        write_audit_log("USER_DELETE", self.current_user, f"user:{user_id}", user["username"], self.request.remote_ip or "")
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
            write_audit_log("USER_TOGGLE", self.current_user, f"user:{user_id}", f"enabled={status}", self.request.remote_ip or "")
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
        if not _reserve_password_attempt(rate_key, now):
            self.write('<script>alert("操作过于频繁，请5分钟后再试");window.history.back();</script>')
            return

        if not old_password or not new_password:
            self.write('<script>alert("请填写所有字段");window.history.back();</script>')
            return
        if new_password != confirm_password:
            self.write('<script>alert("两次输入的新密码不一致");window.history.back();</script>')
            return
        if len(new_password) < 8:
            self.write('<script>alert("新密码长度不能少于8个字符");window.history.back();</script>')
            return

        user = UserRepository.get_user_by_username(self.current_user)
        if not user:
            self.write('<script>alert("用户不存在");window.history.back();</script>')
            return

        ok, msg = UserRepository.update_password(user["id"], old_password, new_password)
        if ok:
            # 成功后清除速率记录
            with _pwd_change_lock:
                _pwd_change_attempts.pop(rate_key, None)
            write_audit_log(
                action="CHANGE_PASSWORD",
                username=self.current_user,
                target=f"user:{user['id']}",
                detail="密码修改成功",
                client_ip=self.request.remote_ip or "",
            )
            self.write('<p>密码修改成功，请重新登录。</p><p><a href="/logout">前往登录页</a></p>')
        else:
            # 记录失败尝试
            write_audit_log(
                action="CHANGE_PASSWORD_FAILED",
                username=self.current_user,
                target=f"user:{user['id']}",
                detail=f"失败原因: {msg}",
                client_ip=self.request.remote_ip or "",
            )
            self.set_status(400)
            self.write(f'<p>{xhtml_escape(msg)}</p><p><a href="javascript:history.back()">返回</a></p>')
