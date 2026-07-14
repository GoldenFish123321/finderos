"""
admin_function.py — 功能管理控制器

系统管理员管理功能模块（新增/编辑/删除/启用禁用/分页）。
"""

import tornado.web
from app.controllers.admin_base import AdminBaseHandler
from app.models.function import FunctionRepository


class FunctionListHandler(AdminBaseHandler):
    """功能列表页"""

    @tornado.web.authenticated
    def get(self):
        page = int(self.get_query_argument("page", 1))
        rows, total = FunctionRepository.get_all(page=page, page_size=20)
        total_pages = max(1, (total + 20 - 1) // 20)

        self.render(
            "admin/function_list.html",
            title="功能管理 — 瞭望与问数系统",
            username=self.current_user,
            functions=rows,
            page=page,
            total=total,
            total_pages=total_pages,
        )


class FunctionFormHandler(AdminBaseHandler):
    """功能新增/编辑表单页"""

    @tornado.web.authenticated
    def get(self):
        func_id = self.get_query_argument("id", None)
        func = None
        if func_id:
            try:
                func = FunctionRepository.get_by_id(int(func_id))
            except (ValueError, TypeError):
                self.write('<script>alert("无效的功能ID");window.history.back();</script>')
                return
            if not func:
                self.write('<script>alert("功能不存在");window.history.back();</script>')
                return

        parents = FunctionRepository.get_parent_options()

        self.render(
            "admin/function_form.html",
            title="编辑功能" if func else "新增功能",
            username=self.current_user,
            func=func,
            parents=parents,
        )

    @tornado.web.authenticated
    def post(self):
        func_id = self.get_body_argument("id", None)
        name = self.get_body_argument("name", "").strip()
        icon = self.get_body_argument("icon", "").strip()
        route_path = self.get_body_argument("route_path", "").strip()
        parent_id_raw = self.get_body_argument("parent_id", "").strip()
        try:
            parent_id = int(parent_id_raw) if parent_id_raw else None
            sort_order = int(self.get_body_argument("sort_order", 0))
        except (ValueError, TypeError):
            self.write('<script>alert("参数格式不正确");window.history.back();</script>')
            return

        if not name:
            self.write('<script>alert("功能名称不能为空");window.history.back();</script>')
            return

        if func_id:  # 编辑
            ok = FunctionRepository.update(
                int(func_id), name, icon, route_path, parent_id, sort_order
            )
            if ok:
                self.redirect("/admin/function?msg=更新成功")
            else:
                self.write('<script>alert("更新失败");window.history.back();</script>')
        else:  # 新增
            FunctionRepository.create(name, icon, route_path, parent_id, sort_order)
            self.redirect("/admin/function?msg=创建成功")


class FunctionDeleteHandler(AdminBaseHandler):
    """删除功能"""

    @tornado.web.authenticated
    def post(self):
        func_id = int(self.get_body_argument("id", 0))
        FunctionRepository.delete(func_id)
        self.redirect("/admin/function?msg=已删除")


class FunctionToggleHandler(AdminBaseHandler):
    """启用/禁用功能"""

    @tornado.web.authenticated
    def post(self):
        func_id = int(self.get_body_argument("id", 0))
        status = FunctionRepository.toggle_enabled(func_id)
        if status == -1:
            self.write('<script>alert("功能不存在");window.history.back();</script>')
        else:
            self.redirect(f"/admin/function?msg={'已启用' if status == 1 else '已禁用'}")
