"""
admin_watch.py — 瞭望采集控制器

A区: 搜索框 + 采集按钮（居中）
B区: 瞭望源规则列表（含参数配置）
C区: 采集结果展示区（百度新闻解析 + 全选/保存到数据仓库）

采集服务委托给 app.services.collector（按教学视频架构）。
"""
import asyncio
import atexit
import concurrent.futures
import json
import logging
import urllib.parse
import tornado.iostream
import tornado.web
from app.controllers.admin_base import AdminBaseHandler
from app.models.watch_source import WatchSourceRepository, resolve_source_parser
from app.models.watch_result import WatchResultRepository
from app.models.data_warehouse import DataWarehouseRepository
from app.utils.security import has_crlf, write_audit_log

logger = logging.getLogger(__name__)

# 采集线程池（模块级复用，避免阻塞 Tornado IOLoop）
_watch_collect_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="watch-collect")
atexit.register(_watch_collect_executor.shutdown, wait=True)

# 深度采集线程池（模块级复用，避免每个请求创建销毁）
_watch_deep_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="watch-deep")
atexit.register(_watch_deep_executor.shutdown, wait=True)
from app.services.collector import fetch_and_parse_via_handler


# 向后兼容别名
parse_baidu_news_html = None  # deprecated, use app.services.collector instead


_SKIPPED_COLLECT_HEADERS = {
    "accept-encoding", "host",
    "sec-fetch-dest", "sec-fetch-mode",
    "sec-fetch-site", "sec-fetch-user",
    "connection", "cache-control",
}


def _split_source_ids(raw_value: str) -> list[str]:
    """解析逗号分隔/数组序列化后的 source_ids。"""
    return [s.strip() for s in (raw_value or "").split(",") if s.strip()]


def _normalize_source_ids(source_ids: list[str] | None) -> list[str]:
    """无显式选择时默认采集所有启用瞭望源。"""
    if source_ids:
        return source_ids
    sources = WatchSourceRepository.get_enabled()
    return [str(s["id"]) for s in sources]


def _get_collect_request(source: dict, keyword: str) -> tuple[str, dict, str]:
    """构建单个瞭望源的请求 URL、请求头与解析器名称。"""
    sid = source["id"]
    url_template = source["url_template"]
    encoded_kw = urllib.parse.quote(keyword, encoding="utf-8")
    request_url = url_template.replace("{keyword}", encoded_kw).replace("{page}", "0")

    raw_headers = WatchSourceRepository.get_headers(sid)
    headers = {}
    for k, v in raw_headers.items():
        if k.lower() in _SKIPPED_COLLECT_HEADERS:
            continue
        if has_crlf(k) or has_crlf(v):
            logger.warning(f"CRLF injection detected in header '{k}' for source {sid}, skipping")
            continue
        headers[k] = v

    parser = resolve_source_parser(source)
    return request_url, headers, parser


def _collect_source(keyword: str, source_id: int) -> dict:
    """采集单个瞭望源并持久化结果（通过统一出口 fetch_and_parse_via_handler）。"""
    source = WatchSourceRepository.get_by_id(source_id)
    if not source or source["is_enabled"] == 0:
        return {
            "source_id": source_id,
            "source_name": "",
            "request_url": "",
            "status": 0,
            "size": 0,
            "news": [],
            "result": {"source_name": "", "status": 0, "error": "瞭望源不存在或已禁用"},
            "ok": False,
        }

    url_template = source.get("url_template", "")
    parser = resolve_source_parser(source)
    request_url = url_template.replace("{keyword}", keyword).replace("{page}", "0")
    try:
        status, size, text, parsed_news = fetch_and_parse_via_handler(
            source_id=source_id, keyword=keyword, page=0, parser=parser,
        )
    except Exception as e:
        logger.error(f"瞭望采集失败: source={source_id}, keyword={keyword}, error={e}", exc_info=True)
        return {
            "source_id": source_id,
            "source_name": source["name"],
            "request_url": request_url,
            "status": 0,
            "size": 0,
            "news": [],
            "result": {
                "source_name": source["name"],
                "status": 0,
                "error": str(e),
            },
            "ok": False,
        }

    news_items = []
    if parsed_news:
        for news in parsed_news:
            news_link = news.get("link", "")
            result_id, is_new = WatchResultRepository.create_if_not_exists(
                source_id=source_id,
                keyword=keyword,
                request_url=news_link or request_url,
                response_status=status,
                response_size=len(json.dumps(news, ensure_ascii=False).encode("utf-8")),
                result_data=json.dumps(news, ensure_ascii=False),
            )
            if is_new:
                news_items.append({
                    "id": result_id,
                    "title": news.get("title", ""),
                    "link": news_link,
                    "summary": news.get("summary", ""),
                    "source_name": news.get("source_name", source["name"]),
                })
        collect_result = {
            "source_name": source["name"],
            "status": status,
            "news_count": len(parsed_news),
        }
    else:
        result_id, _ = WatchResultRepository.create_if_not_exists(
            source_id=source_id,
            keyword=keyword,
            request_url=request_url,
            response_status=status,
            response_size=size,
            result_data=text[:10000] if len(text) > 10000 else text,
        )
        collect_result = {
            "source_name": source["name"],
            "status": status,
            "size": size,
            "id": result_id,
        }

    return {
        "source_id": source_id,
        "source_name": source["name"],
        "request_url": request_url,
        "status": status,
        "size": size,
        "news": news_items,
        "result": collect_result,
        "ok": 200 <= int(status or 0) < 400,
    }


def _write_collect_audit(username: str, keyword: str, source_count: int,
                         news_count: int, success_count: int, failed_count: int,
                         client_ip: str) -> None:
    """记录采集审计日志，供采集日志页查询。"""
    write_audit_log(
        action="WATCH_COLLECT",
        username=username,
        target="watch",
        detail=(
            f"keyword={keyword}, sources={source_count}, total_news={news_count}, "
            f"success={success_count}, failed={failed_count}"
        ),
        client_ip=client_ip or "",
    )


class WatchHandler(AdminBaseHandler):
    """瞭望采集主页面"""

    @tornado.web.authenticated
    def get(self):
        keyword = self.get_query_argument("keyword", "").strip()
        try:
            page = int(self.get_query_argument("page", 1))
        except (ValueError, TypeError):
            page = 1
        source_id = self.get_query_argument("source_id", None)
        if source_id:
            try:
                source_id = int(source_id)
            except (ValueError, TypeError):
                source_id = None

        sources = WatchSourceRepository.get_enabled()
        rows, total = WatchResultRepository.get_all(
            page=page, page_size=12, keyword=keyword, source_id=source_id
        )
        total_pages = max(1, (total + 12 - 1) // 12)
        stats = WatchResultRepository.get_stats()

        self.render(
            "admin/watch.html",
            title="瞭望采集 — 瞭望与问数系统",
            username=self.current_user,
            sources=sources,
            results=rows,
            page=page,
            total=total,
            total_pages=total_pages,
            keyword=keyword,
            active_source_id=source_id,
            saved_count=stats["saved"],
            xsrf_token=self.xsrf_token.decode() if isinstance(self.xsrf_token, bytes) else self.xsrf_token,
        )

    @tornado.web.authenticated
    def post(self):
        """执行采集：关键词 → 按启用的瞭望源发起请求 → 解析 → 返回结构化结果"""
        keyword = self.get_body_argument("keyword", "").strip()
        # 兼容 jQuery 数组序列化 (source_ids[]=1&source_ids[]=2) 和逗号分隔格式
        source_ids_raw_list = self.get_body_arguments("source_ids") or self.get_body_arguments("source_ids[]")
        if source_ids_raw_list:
            # 将多个值用逗号连接，再统一按逗号拆分
            source_ids_raw = ",".join(source_ids_raw_list)
        else:
            source_ids_raw = self.get_body_argument("source_ids", "") or self.get_body_argument("source_ids[]", "")
        source_ids = [s.strip() for s in source_ids_raw.split(",") if s.strip()] if source_ids_raw else []

        if not keyword:
            self.write({"code": 1, "msg": "请输入关键词"})
            return

        source_ids = _normalize_source_ids(source_ids)
        all_news = []
        collect_results = []
        success_count = 0
        failed_count = 0

        for sid in source_ids:
            try:
                sid = int(sid)
            except (ValueError, TypeError):
                continue
            item = _collect_source(keyword, sid)
            all_news.extend(item["news"])
            collect_results.append(item["result"])
            if item["ok"]:
                success_count += 1
            else:
                failed_count += 1

        _write_collect_audit(
            self.current_user, keyword, len(source_ids), len(all_news),
            success_count, failed_count, self.request.remote_ip or "",
        )

        self.write({
            "code": 0,
            "msg": f"采集完成，共获取 {len(all_news)} 条新闻",
            "news": all_news,
            "results": collect_results,
            "total": len(all_news),
        })


class WatchStreamHandler(AdminBaseHandler):
    """采集进度 SSE 推送接口。"""

    def _write_sse(self, event: str, data: dict) -> None:
        self.write(f"event: {event}\n")
        self.write(f"data: {json.dumps(data, ensure_ascii=False)}\n\n")

    @tornado.web.authenticated
    async def get(self):
        # SSE 使用 GET，但该接口会触发采集并写库；需手动执行 XSRF 校验。
        self.check_xsrf_cookie()
        keyword = self.get_query_argument("keyword", "").strip()
        source_ids = _split_source_ids(self.get_query_argument("source_ids", ""))

        self.set_header("Content-Type", "text/event-stream; charset=utf-8")
        self.set_header("Cache-Control", "no-cache")
        self.set_header("Connection", "keep-alive")
        self.set_header("X-Accel-Buffering", "no")

        async def emit(event: str, data: dict):
            self._write_sse(event, data)
            await self.flush()

        try:
            if not keyword:
                await emit("collect_error", {"code": 1, "msg": "请输入关键词"})
                self.finish()
                return

            source_ids = _normalize_source_ids(source_ids)
            numeric_source_ids = []
            for sid in source_ids:
                try:
                    numeric_source_ids.append(int(sid))
                except (ValueError, TypeError):
                    continue

            total_sources = len(numeric_source_ids)
            if total_sources == 0:
                await emit("collect_error", {"code": 1, "msg": "暂无可用瞭望源"})
                self.finish()
                return

            await emit("collect_progress", {
                "percent": 0,
                "current_url": "",
                "success": 0,
                "failed": 0,
                "message": "开始采集",
            })

            all_news = []
            collect_results = []
            success_count = 0
            failed_count = 0
            loop = asyncio.get_event_loop()

            for index, sid in enumerate(numeric_source_ids, start=1):
                source = WatchSourceRepository.get_by_id(sid)
                if source and source["is_enabled"] == 1:
                    request_url, _, _ = _get_collect_request(source, keyword)
                    source_name = source["name"]
                else:
                    request_url = ""
                    source_name = ""

                await emit("collect_progress", {
                    "percent": int((index - 1) / total_sources * 100),
                    "current_url": request_url,
                    "source_name": source_name,
                    "success": success_count,
                    "failed": failed_count,
                    "message": f"正在采集 {source_name or sid}",
                })

                item = await loop.run_in_executor(
                    _watch_collect_executor, _collect_source, keyword, sid
                )
                all_news.extend(item["news"])
                collect_results.append(item["result"])
                if item["ok"]:
                    success_count += 1
                else:
                    failed_count += 1

                await emit("collect_progress", {
                    "percent": int(index / total_sources * 100),
                    "current_url": item["request_url"],
                    "source_name": item["source_name"],
                    "success": success_count,
                    "failed": failed_count,
                    "message": f"已完成 {index}/{total_sources}",
                })

            _write_collect_audit(
                self.current_user, keyword, total_sources, len(all_news),
                success_count, failed_count, self.request.remote_ip or "",
            )

            await emit("collect_done", {
                "code": 0,
                "msg": f"采集完成，共获取 {len(all_news)} 条新闻",
                "news": all_news,
                "results": collect_results,
                "total": len(all_news),
                "success": success_count,
                "failed": failed_count,
            })
        except tornado.iostream.StreamClosedError:
            logger.info("采集 SSE 连接已关闭")
            return
        except Exception as e:
            logger.error(f"采集 SSE 异常: {e}", exc_info=True)
            try:
                await emit("collect_error", {"code": 1, "msg": f"采集异常: {e}"})
            except tornado.iostream.StreamClosedError:
                return
        finally:
            if not self._finished:
                self.finish()


class WatchSaveHandler(AdminBaseHandler):
    """保存选中的采集结果到数据仓库（含 URL 去重，v0.2 同时写入独立 data_warehouse 表）"""

    @tornado.web.authenticated
    def post(self):
        # 兼容四种前端传参格式：
        # 1. jQuery默认数组序列化: result_ids[]=1&result_ids[]=2
        # 2. 多个同名表单字段: result_ids=1&result_ids=2
        # 3. 逗号分隔字符串: result_ids=1,2
        # 4. JSON body: {"result_ids": [1,2]}
        raw_ids = (self.get_body_arguments("result_ids")
                   or self.get_body_arguments("result_ids[]"))
        if not raw_ids:
            # 尝试从逗号分隔字符串或 JSON body 解析
            ids_str = self.get_body_argument("result_ids", "")
            if not ids_str:
                ids_str = self.get_body_argument("result_ids[]", "")
            if ids_str:
                raw_ids = [ids_str]
            else:
                # 尝试 JSON body
                try:
                    body = json.loads(self.request.body)
                    if isinstance(body, dict) and "result_ids" in body:
                        raw_ids = body["result_ids"]
                        if isinstance(raw_ids, (int, str)):
                            raw_ids = [str(raw_ids)]
                        else:
                            raw_ids = [str(x) for x in raw_ids]
                except (json.JSONDecodeError, TypeError, AttributeError):
                    pass

        # 统一展开：对每个元素按逗号拆分，兼容混合格式
        result_ids = []
        for r in raw_ids:
            for part in str(r).split(","):
                part = part.strip()
                if part:
                    result_ids.append(part)

        if not result_ids:
            self.write({"code": 1, "msg": "请选择要保存的结果"})
            return

        ids = [int(rid) for rid in result_ids if rid]

        # v0.2: 先写入独立 data_warehouse 表，成功后再标记 SAVED（避免解析失败导致错误标记）
        dw_count = 0
        saved_ids = []
        for rid in ids:
            result = WatchResultRepository.get_by_id(rid)
            if not result:
                continue
            result_data = result["result_data"] or ""
            if result_data.startswith("SAVED:"):
                result_data = result_data[6:]  # 去掉前缀
            # 尝试解析 JSON 提取标题/链接/摘要（兼容单个 dict 和 list 两种格式）
            items = []
            try:
                items = json.loads(result_data)
            except (json.JSONDecodeError, TypeError):
                pass
            # 统一处理：单个 dict 包装为 list，list 直接使用
            if isinstance(items, dict):
                items = [items]
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        if DataWarehouseRepository.create(
                            result_id=rid,
                            title=item.get("title", ""),
                            link=item.get("link", ""),
                            summary=item.get("summary", ""),
                            source_name=item.get("source_name", ""),
                            raw_data=json.dumps(item, ensure_ascii=False),
                        ):
                            dw_count += 1
                            if rid not in saved_ids:
                                saved_ids.append(rid)

        # 只有成功写入数据仓库后才标记 SAVED（避免数据解析失败导致虚假的 SAVED 标记）
        saved, skipped = 0, len(ids)
        if saved_ids:
            saved, skipped = WatchResultRepository.mark_saved_batch(saved_ids)

        if dw_count > 0:
            msg = f"成功保存 {dw_count} 条结果到数据仓库"
            if skipped > 0:
                msg += f"（跳过 {skipped} 条重复/已保存）"
        else:
            msg = f"所有 {skipped} 条结果已存在或已保存，无需重复操作"

        self.write({"code": 0, "msg": msg})


class WatchDeepCollectHandler(AdminBaseHandler):
    """瞭望采集页一站式深度采集（v0.2 新增）

    选中采集结果 → 保存到数据仓库 → 立即深度采集正文内容。
    用户无需先跳转到数据仓库页面再操作。
    """

    @tornado.web.authenticated
    async def post(self):
        import asyncio
        import concurrent.futures

        # 解析 result_ids（复用 WatchSaveHandler 的兼容逻辑）
        raw_ids = (self.get_body_arguments("result_ids")
                   or self.get_body_arguments("result_ids[]"))
        if not raw_ids:
            ids_str = self.get_body_argument("result_ids", "")
            if not ids_str:
                ids_str = self.get_body_argument("result_ids[]", "")
            if ids_str:
                raw_ids = [ids_str]
            else:
                try:
                    body = json.loads(self.request.body)
                    if isinstance(body, dict) and "result_ids" in body:
                        raw_ids = body["result_ids"]
                        if isinstance(raw_ids, (int, str)):
                            raw_ids = [str(raw_ids)]
                        else:
                            raw_ids = [str(x) for x in raw_ids]
                except (json.JSONDecodeError, TypeError, AttributeError):
                    pass

        result_ids = []
        for r in raw_ids:
            for part in str(r).split(","):
                part = part.strip()
                if part:
                    result_ids.append(part)

        if not result_ids:
            self.write({"code": 1, "msg": "请选择要深度采集的结果"})
            return

        ids = [int(rid) for rid in result_ids if rid]
        if not ids:
            self.write({"code": 1, "msg": "无效的结果 ID"})
            return

        # 最多处理 5 条，避免超时
        ids = ids[:5]

        saved_dw_ids = []
        saved_rids = set()  # 追踪哪些 rid 有数据成功写入 data_warehouse
        # 使用单个连接完成所有检查+写入，避免嵌套 get_db() 死锁
        from app.models.db import get_db
        with get_db() as conn:
            for rid in ids:
                # 直接使用当前连接查询，避免嵌套 get_db()
                result = conn.execute(
                    "SELECT wr.*, ws.name as source_name "
                    "FROM watch_results wr LEFT JOIN watch_sources ws ON wr.source_id = ws.id "
                    "WHERE wr.id = ?", (rid,)
                ).fetchone()
                if not result:
                    continue
                result_data = result["result_data"] or ""
                if result_data.startswith("SAVED:"):
                    result_data = result_data[6:]
                items = []
                try:
                    items = json.loads(result_data)
                except (json.JSONDecodeError, TypeError):
                    pass
                if isinstance(items, dict):
                    items = [items]
                if isinstance(items, list):
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        link = item.get("link", "")
                        title = item.get("title", "")
                        source_name = item.get("source_name", "")

                        # 检查是否已存在（同一连接内完成）
                        existing = None
                        if link:
                            existing = conn.execute(
                                "SELECT id FROM data_warehouse WHERE link = ?", (link,)
                            ).fetchone()
                        if not existing and title:
                            existing = conn.execute(
                                "SELECT id FROM data_warehouse WHERE title = ? AND source_name = ?",
                                (title, source_name),
                            ).fetchone()

                        if existing:
                            if existing["id"] not in saved_dw_ids:
                                saved_dw_ids.append(existing["id"])
                            continue

                        # 立即插入
                        try:
                            raw_json = json.dumps(item, ensure_ascii=False)
                            conn.execute(
                                "INSERT OR IGNORE INTO data_warehouse "
                                "(result_id, title, link, summary, source_name, raw_data) "
                                "VALUES (?, ?, ?, ?, ?, ?)",
                                (rid, title, link, item.get("summary", ""),
                                 source_name, raw_json),
                            )
                            # 获取新插入的 ID
                            if link:
                                new_row = conn.execute(
                                    "SELECT id FROM data_warehouse WHERE link = ? ORDER BY id DESC LIMIT 1",
                                    (link,),
                                ).fetchone()
                            else:
                                new_row = conn.execute(
                                    "SELECT id FROM data_warehouse WHERE title = ? AND source_name = ? ORDER BY id DESC LIMIT 1",
                                    (title, source_name),
                                ).fetchone()
                            if new_row:
                                if new_row["id"] not in saved_dw_ids:
                                    saved_dw_ids.append(new_row["id"])
                                saved_rids.add(rid)
                        except Exception as e:
                            logger.error(f"深度采集: 插入数据仓库记录失败 (rid={rid}): {e}", exc_info=True)
            conn.commit()

        # 只有成功写入数据仓库后才标记 SAVED（仅标记有数据成功入库的 rid）
        if saved_rids:
            WatchResultRepository.mark_saved_batch(list(saved_rids))

        if not saved_dw_ids:
            self.write({"code": 1, "msg": "保存到数据仓库失败，请检查数据"})
            return

        # 步骤2：对每个已保存的仓库记录执行深度采集
        from app.services.deep_collector import deep_fetch_and_save

        success_count = 0
        fail_count = 0
        already_count = 0
        loop = asyncio.get_event_loop()

        for dw_id in saved_dw_ids:
                # 获取 link 和采集状态（同一连接）
                with get_db() as conn:
                    record = conn.execute(
                        "SELECT id, link, is_deep_collected FROM data_warehouse WHERE id = ?",
                        (dw_id,),
                    ).fetchone()
                if not record or not record["link"]:
                    fail_count += 1
                    continue
                if record["is_deep_collected"] == 1:
                    already_count += 1
                    continue

                success, msg = await loop.run_in_executor(
                    _watch_deep_executor, deep_fetch_and_save, dw_id, record["link"]
                )
                if success:
                    success_count += 1
                else:
                    fail_count += 1

        # 审计日志
        from app.utils.security import write_audit_log
        write_audit_log(
            action="WATCH_DEEP_COLLECT",
            username=self.current_user,
            target=f"watch_results:{','.join(str(x) for x in ids[:5])}",
            detail=f"saved={len(saved_dw_ids)}, deep_ok={success_count}, deep_fail={fail_count}",
            client_ip=self.request.remote_ip or "",
        )

        summary = f"保存 {len(saved_dw_ids)} 条，深度采集成功 {success_count} 条"
        if already_count > 0:
            summary += f"，{already_count} 条已采集跳过"
        if fail_count > 0:
            summary += f"，失败 {fail_count} 条"
        self.write({"code": 0, "msg": summary})
