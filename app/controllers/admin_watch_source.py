"""
admin_watch_source.py — 瞭源管理控制器

管理数据采集来源（瞭望源）的 CRUD 操作。
"""
import tornado.web
from app.controllers.admin_base import AdminBaseHandler
from app.models.watch_source import WatchSourceRepository


class WatchSourceListHandler(AdminBaseHandler):
    """瞭源管理列表页"""

    @tornado.web.authenticated
    def get(self):
        page = int(self.get_query_argument("page", 1))
        keyword = self.get_query_argument("keyword", "").strip()
        rows, total = WatchSourceRepository.get_all(
            page=page, page_size=20, keyword=keyword
        )
        total_pages = max(1, (total + 20 - 1) // 20)

        self.render(
            "admin/watch_source_list.html",
            title="瞭源管理 — 瞭望与问数系统",
            username=self.current_user,
            sources=rows,
            page=page,
            total=total,
            total_pages=total_pages,
            keyword=keyword,
            msg=self.get_query_argument("msg", ""),
        )


class WatchSourceFormHandler(AdminBaseHandler):
    """瞭源管理新增/编辑表单"""

    @tornado.web.authenticated
    def get(self):
        source_id = self.get_query_argument("id", None)
        source = None
        if source_id:
            try:
                source = WatchSourceRepository.get_by_id(int(source_id))
            except (ValueError, TypeError):
                self.write('<script>alert("无效的瞭望源ID");window.history.back();</script>')
                return
            if not source:
                self.write('<script>alert("瞭望源不存在");window.history.back();</script>')
                return

        self.render(
            "admin/watch_source_form.html",
            title="编辑瞭望源" if source else "新增瞭望源",
            username=self.current_user,
            source=source,
        )

    @tornado.web.authenticated
    def post(self):
        source_id = self.get_body_argument("id", None)
        name = self.get_body_argument("name", "").strip()
        description = self.get_body_argument("description", "").strip()
        url_template = self.get_body_argument("url_template", "").strip()
        request_headers = self.get_body_argument("request_headers", "{}").strip()
        try:
            sort_order = int(self.get_body_argument("sort_order", 0))
        except (ValueError, TypeError):
            self.write('<script>alert("排序号格式不正确");window.history.back();</script>')
            return

        if not name or not url_template:
            self.write('<script>alert("名称和URL模板不能为空");window.history.back();</script>')
            return

        if source_id:
            ok = WatchSourceRepository.update(
                int(source_id), name, description, url_template, request_headers, sort_order
            )
            msg = "更新成功" if ok else "更新失败"
        else:
            ok = WatchSourceRepository.create(
                name, description, url_template, request_headers, sort_order
            )
            msg = "创建成功" if ok else "创建失败"

        self.redirect(f"/admin/watch/source?msg={msg}")


class WatchSourceDeleteHandler(AdminBaseHandler):
    """删除瞭望源"""

    @tornado.web.authenticated
    def post(self):
        source_id = int(self.get_body_argument("id", 0))
        WatchSourceRepository.delete(source_id)
        self.redirect("/admin/watch/source?msg=已删除")


class WatchSourceToggleHandler(AdminBaseHandler):
    """启用/禁用瞭望源"""

    @tornado.web.authenticated
    def post(self):
        source_id = int(self.get_body_argument("id", 0))
        status = WatchSourceRepository.toggle_enabled(source_id)
        if status == -1:
            self.write('<script>alert("瞭望源不存在");window.history.back();</script>')
        else:
            self.redirect(
                f"/admin/watch/source?msg={'已启用' if status == 1 else '已禁用'}"
            )
