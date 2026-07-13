"""
admin_warehouse.py — 数据仓库控制器

管理和展示瞭望采集的历史结果数据。
"""
import json
import tornado.web
from app.controllers.admin_base import AdminBaseHandler
from app.models.watch_result import WatchResultRepository


class WarehouseHandler(AdminBaseHandler):
    """数据仓库列表页"""

    @tornado.web.authenticated
    def get(self):
        page = int(self.get_query_argument("page", 1))
        keyword = self.get_query_argument("keyword", "").strip()
        source_id = self.get_query_argument("source_id", None)
        if source_id:
            source_id = int(source_id)

        rows, total = WatchResultRepository.get_all(
            page=page, page_size=20, keyword=keyword, source_id=source_id
        )
        total_pages = max(1, (total + 20 - 1) // 20)
        stats = WatchResultRepository.get_stats()

        self.render(
            "admin/warehouse.html",
            title="数据仓库 — 瞭望与问数系统",
            username=self.current_user,
            results=rows,
            page=page,
            total=total,
            total_pages=total_pages,
            keyword=keyword,
            stats=stats,
            xsrf_token=self.xsrf_token.decode() if isinstance(self.xsrf_token, bytes) else self.xsrf_token,
        )


class WarehouseDetailHandler(AdminBaseHandler):
    """数据仓库详情页"""

    @tornado.web.authenticated
    def get(self):
        result_id = int(self.get_query_argument("id", 0))
        result = WatchResultRepository.get_by_id(result_id)
        if not result:
            self.write('<script>alert("记录不存在");window.history.back();</script>')
            return

        self.render(
            "admin/warehouse_detail.html",
            title="采集详情 — 瞭望与问数系统",
            username=self.current_user,
            result=result,
        )


class WarehouseDeleteHandler(AdminBaseHandler):
    """删除采集结果"""

    @tornado.web.authenticated
    def post(self):
        result_id = int(self.get_body_argument("id", 0))
        WatchResultRepository.delete(result_id)
        self.redirect("/admin/warehouse?msg=已删除")


class WarehouseBatchDeleteHandler(AdminBaseHandler):
    """批量删除采集结果"""

    @tornado.web.authenticated
    def post(self):
        ids_str = self.get_body_argument("ids", "")
        if not ids_str:
            self.write({"code": 1, "msg": "请选择要删除的记录"})
            return
        try:
            ids = [int(x) for x in ids_str.split(",") if x.strip()]
            count = 0
            for rid in ids:
                WatchResultRepository.delete(rid)
                count += 1
            self.write({"code": 0, "msg": f"成功删除 {count} 条记录"})
        except (ValueError, TypeError):
            self.write({"code": 1, "msg": "参数格式错误"})
