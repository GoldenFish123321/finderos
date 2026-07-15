"""
admin_warehouse.py — 数据仓库控制器

管理和展示瞭望采集的历史结果数据。
v0.2: 支持独立的 data_warehouse 表查询（借鉴郭家琪）。
v0.2: 新增深度采集功能（DeepCollectHandler）。
"""
import atexit
import json
import concurrent.futures
import tornado.web
from app.controllers.admin_base import AdminBaseHandler
from app.models.db import get_db
from app.models.watch_result import WatchResultRepository
from app.models.data_warehouse import DataWarehouseRepository

# 深度采集专用线程池（复用，避免每个请求创建销毁）
_deep_collect_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="deep-collect")
atexit.register(_deep_collect_executor.shutdown, wait=True)


class WarehouseHandler(AdminBaseHandler):
    """数据仓库列表页（v0.2: 使用独立 data_warehouse 表）"""

    @tornado.web.authenticated
    def get(self):
        try:
            page = int(self.get_query_argument("page", 1))
        except (ValueError, TypeError):
            page = 1
        keyword = self.get_query_argument("keyword", "").strip()
        source_id = self.get_query_argument("source_id", None)
        if source_id:
            try:
                source_id = int(source_id)
            except (ValueError, TypeError):
                source_id = None

        rows, total = DataWarehouseRepository.get_all(
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


class WatchLogHandler(AdminBaseHandler):
    """采集日志页：从 audit_logs 读取采集相关记录。"""

    @tornado.web.authenticated
    def get(self):
        try:
            page = int(self.get_query_argument("page", 1))
        except (ValueError, TypeError):
            page = 1
        page = max(1, page)
        keyword = self.get_query_argument("keyword", "").strip()
        page_size = 20

        where = ["UPPER(action) LIKE ?"]
        params = ["%COLLECT%"]
        if keyword:
            like = f"%{keyword}%"
            where.append("(action LIKE ? OR username LIKE ? OR target LIKE ? OR detail LIKE ? OR client_ip LIKE ?)")
            params.extend([like, like, like, like, like])
        where_sql = "WHERE " + " AND ".join(where)

        with get_db() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) as cnt FROM audit_logs {where_sql}",
                params,
            ).fetchone()["cnt"]
            logs = conn.execute(
                f"""
                SELECT id, action, username, target, detail, client_ip, created_at
                FROM audit_logs
                {where_sql}
                ORDER BY id DESC
                LIMIT ? OFFSET ?
                """,
                (*params, page_size, (page - 1) * page_size),
            ).fetchall()

            stats = {
                "total": total,
                "watch_collect": conn.execute(
                    "SELECT COUNT(*) as cnt FROM audit_logs WHERE action = ?",
                    ("WATCH_COLLECT",),
                ).fetchone()["cnt"],
                "deep_collect": conn.execute(
                    "SELECT COUNT(*) as cnt FROM audit_logs WHERE UPPER(action) LIKE ? AND action != ?",
                    ("%COLLECT%", "WATCH_COLLECT"),
                ).fetchone()["cnt"],
            }

        total_pages = max(1, (total + page_size - 1) // page_size)
        self.render(
            "admin/watch_log.html",
            title="采集日志 — 瞭望与问数系统",
            username=self.current_user,
            logs=logs,
            page=page,
            total=total,
            total_pages=total_pages,
            keyword=keyword,
            stats=stats,
            xsrf_token=self.xsrf_token.decode() if isinstance(self.xsrf_token, bytes) else self.xsrf_token,
        )


class WarehouseDetailHandler(AdminBaseHandler):
    """数据仓库详情页（v0.2: 使用独立 data_warehouse 表，v0.2: 展示深度采集内容）"""

    @tornado.web.authenticated
    def get(self):
        try:
            result_id = int(self.get_query_argument("id", 0))
        except (ValueError, TypeError):
            self.write('<script>alert("无效的记录ID");window.history.back();</script>')
            return
        result = DataWarehouseRepository.get_by_id(result_id)
        if not result:
            self.write('<script>alert("记录不存在");window.history.back();</script>')
            return

        # 解析深度采集内容供模板使用
        deep_content = ""
        try:
            raw_data = result["raw_data"] or ""
            if raw_data:
                raw_obj = json.loads(raw_data)
                if isinstance(raw_obj, dict):
                    deep_content = raw_obj.get("deep_content", "")
        except (KeyError, TypeError, json.JSONDecodeError):
            pass

        self.render(
            "admin/warehouse_detail.html",
            title="采集详情 — 瞭望与问数系统",
            username=self.current_user,
            result=result,
            deep_content=deep_content,
            xsrf_token=self.xsrf_token.decode() if isinstance(self.xsrf_token, bytes) else self.xsrf_token,
        )


class WarehouseDeleteHandler(AdminBaseHandler):
    """删除采集结果（v0.2: 从 data_warehouse 表删除）"""

    @tornado.web.authenticated
    def post(self):
        result_id = int(self.get_body_argument("id", 0))
        DataWarehouseRepository.delete(result_id)
        self.redirect("/admin/warehouse?msg=已删除")


class WarehouseBatchDeleteHandler(AdminBaseHandler):
    """批量删除采集结果（v0.2: 从 data_warehouse 表批量删除）"""

    @tornado.web.authenticated
    def post(self):
        ids_str = self.get_body_argument("ids", "")
        if not ids_str:
            self.write({"code": 1, "msg": "请选择要删除的记录"})
            return
        try:
            ids = [int(x) for x in ids_str.split(",") if x.strip()]
            count = DataWarehouseRepository.batch_delete(ids)
            self.write({"code": 0, "msg": f"成功删除 {count} 条记录"})
        except (ValueError, TypeError):
            self.write({"code": 1, "msg": "参数格式错误"})


class WarehouseDeepCollectHandler(AdminBaseHandler):
    """深度采集处理器（v0.2 新增）

    对数据仓库中的链接执行深度内容抓取：
    - GET: 深度采集结果查看（悬浮窗模式数据）
    - POST: 触发深度采集任务
    """

    @tornado.web.authenticated
    def get(self):
        """查看深度采集结果。"""
        try:
            dw_id = int(self.get_query_argument("id", 0))
        except (ValueError, TypeError):
            self.write({"code": 1, "msg": "无效的记录ID"})
            return
        record = DataWarehouseRepository.get_by_id(dw_id)
        if not record:
            self.write({"code": 1, "msg": "记录不存在"})
            return

        # 解析深度采集内容
        deep_content = ""
        try:
            raw_data = record["raw_data"] or ""
            if raw_data:
                raw_obj = json.loads(raw_data)
                if isinstance(raw_obj, dict):
                    deep_content = raw_obj.get("deep_content", "")
        except (KeyError, TypeError, json.JSONDecodeError):
            pass

        self.write({
            "code": 0,
            "id": record["id"],
            "title": record["title"] or "",
            "link": record["link"] or "",
            "source_name": record["source_name"] or "",
            "is_deep_collected": record["is_deep_collected"],
            "deep_collected_at": record["deep_collected_at"] or "",
            "deep_content": deep_content,
        })

    @tornado.web.authenticated
    async def post(self):
        """触发深度采集任务（异步执行）。"""
        import asyncio
        import concurrent.futures

        dw_id = int(self.get_body_argument("id", 0))
        record = DataWarehouseRepository.get_by_id(dw_id)
        if not record:
            self.write({"code": 1, "msg": "记录不存在"})
            return

        link = record["link"] or ""
        if not link:
            self.write({"code": 1, "msg": "该记录没有可采集的链接"})
            return

        # 异步执行深度采集（复用全局线程池，避免阻塞主线程）
        try:
            loop = asyncio.get_event_loop()
            from app.services.deep_collector import deep_fetch_and_save

            success, message = await loop.run_in_executor(
                _deep_collect_executor, deep_fetch_and_save, dw_id, link
            )

            if success:
                from app.utils.security import write_audit_log
                write_audit_log(
                    action="DEEP_COLLECT",
                    username=self.current_user,
                    target=f"warehouse:{dw_id}",
                    detail=f"link={link[:200]}, msg={message}",
                    client_ip=self.request.remote_ip or "",
                )
            self.write({"code": 0 if success else 1, "msg": message})
        except Exception as e:
            self.write({"code": 1, "msg": f"深度采集异常: {e}"})
