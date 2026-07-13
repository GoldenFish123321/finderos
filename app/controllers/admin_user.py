"""
admin_user.py — 用户管理控制器

系统管理员管理所有用户（新增/编辑/删除/禁用/搜索/分页）。
"""

import tornado.web
from app.controllers.admin_base import AdminBaseHandler
from app.models.user import UserRepository
from app.models.role import RoleRepository


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
        )


class UserFormHandler(AdminBaseHandler):
    """用户新增/编辑表单页"""

    @tornado.web.authenticated
    def get(self):
        user_id = self.get_query_argument("id", None)
        user = None
        if user_id:
            user = UserRepository.get_user_by_id(int(user_id))
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
            kwargs = {}
            if username:
                kwargs["username"] = username
            if password:
                kwargs["password"] = password
            kwargs["role_id"] = role_id
            ok = UserRepository.update_user(user_id, **kwargs)
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
        if user and user["username"] == "admin":
            self.write('<script>alert("超级管理员 admin 不可删除");window.history.back();</script>')
            return
        UserRepository.delete_user(user_id)
        self.redirect("/admin/user?msg=已删除")


class UserToggleHandler(AdminBaseHandler):
    """启用/禁用用户"""

    @tornado.web.authenticated
    def post(self):
        user_id = int(self.get_body_argument("id", 0))
        status = UserRepository.toggle_enabled(user_id)
        if status == -2:
            self.write('<script>alert("超级管理员 admin 不可被禁用");window.history.back();</script>')
        elif status == -1:
            self.write('<script>alert("用户不存在");window.history.back();</script>')
        else:
            self.redirect(f"/admin/user?msg={'已启用' if status == 1 else '已禁用'}")
