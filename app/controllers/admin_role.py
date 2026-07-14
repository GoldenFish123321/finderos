"""
admin_role.py — 角色管理控制器

系统管理员管理角色（新增/编辑/删除/分页），角色可与功能树形联动。
"""

import tornado.web
from app.controllers.admin_base import AdminBaseHandler
from app.models.role import RoleRepository
from app.models.function import FunctionRepository


class RoleListHandler(AdminBaseHandler):
    """角色列表页"""

    @tornado.web.authenticated
    def get(self):
        page = int(self.get_query_argument("page", 1))
        rows, total = RoleRepository.get_all(page=page, page_size=20)
        total_pages = max(1, (total + 20 - 1) // 20)

        self.render(
            "admin/role_list.html",
            title="角色管理 — 瞭望与问数系统",
            username=self.current_user,
            roles=rows,
            page=page,
            total=total,
            total_pages=total_pages,
        )


class RoleFormHandler(AdminBaseHandler):
    """角色新增/编辑表单页"""

    @tornado.web.authenticated
    def get(self):
        role_id = self.get_query_argument("id", None)
        role = None
        if role_id:
            try:
                role = RoleRepository.get_by_id(int(role_id))
            except (ValueError, TypeError):
                self.write('<script>alert("无效的角色ID");window.history.back();</script>')
                return
            if not role:
                self.write('<script>alert("角色不存在");window.history.back();</script>')
                return

            # 系统角色不允许编辑
            if role["is_system"] == 1:
                self.write('<script>alert("系统默认角色不可编辑");window.history.back();</script>')
                return

        self.render(
            "admin/role_form.html",
            title="编辑角色" if role else "新增角色",
            username=self.current_user,
            role=role,
            func_tree=FunctionRepository.get_enabled_tree(
                int(role_id) if role else None
            ),
        )

    @tornado.web.authenticated
    def post(self):
        role_id = self.get_body_argument("id", None)
        name = self.get_body_argument("name", "").strip()
        description = self.get_body_argument("description", "").strip()
        function_ids = self.get_body_arguments("function_ids")

        if not name:
            self.write('<script>alert("角色名称不能为空");window.history.back();</script>')
            return

        if role_id:  # 编辑
            role_id = int(role_id)
            role = RoleRepository.get_by_id(role_id)
            if role and role["is_system"] == 1:
                self.write('<script>alert("系统默认角色不可编辑");window.history.back();</script>')
                return
            ok = RoleRepository.update(role_id, name, description)
            if ok:
                # 更新功能关联
                try:
                    func_ids = [int(x) for x in function_ids if x]
                except (ValueError, TypeError):
                    self.write('<script>alert("功能ID格式错误");window.history.back();</script>')
                    return
                RoleRepository.set_functions(role_id, func_ids)
                self.redirect("/admin/role?msg=更新成功")
            else:
                self.write('<script>alert("更新失败，角色名可能重复");window.history.back();</script>')
        else:  # 新增
            ok = RoleRepository.create(name, description)
            if ok:
                # 获取新角色 ID 并关联功能
                new_role = RoleRepository.get_by_name(name)
                if new_role:
                    try:
                        func_ids = [int(x) for x in function_ids if x]
                    except (ValueError, TypeError):
                        self.write('<script>alert("功能ID格式错误");window.history.back();</script>')
                        return
                    RoleRepository.set_functions(new_role["id"], func_ids)
                self.redirect("/admin/role?msg=创建成功")
            else:
                self.write('<script>alert("角色名已存在");window.history.back();</script>')


class RoleDeleteHandler(AdminBaseHandler):
    """删除角色"""

    @tornado.web.authenticated
    def post(self):
        role_id = int(self.get_body_argument("id", 0))
        role = RoleRepository.get_by_id(role_id)
        if not role:
            self.write('<script>alert("角色不存在");window.history.back();</script>')
            return
        if role["is_system"] == 1:
            self.write('<script>alert("系统默认角色不可删除");window.history.back();</script>')
            return
        ok = RoleRepository.delete(role_id)
        if ok:
            self.redirect("/admin/role?msg=已删除")
        else:
            self.write('<script>alert("删除失败：可能有用户正在使用此角色，请先解除关联");window.history.back();</script>')
