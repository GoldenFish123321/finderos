"""
admin_watch.py — 瞭望采集控制器

A区: 搜索框 + 采集按钮（居中）
B区: 瞭望源规则列表（含参数配置）
C区: 采集结果展示区（百度新闻解析 + 全选/保存到数据仓库）

采集服务委托给 app.services.collector（按教学视频架构）。
"""
import json
import logging
import urllib.parse
import tornado.web
from app.controllers.admin_base import AdminBaseHandler
from app.models.watch_source import WatchSourceRepository
from app.models.watch_result import WatchResultRepository
from app.models.data_warehouse import DataWarehouseRepository

logger = logging.getLogger(__name__)
from app.services.collector import fetch_and_parse


# 向后兼容别名
parse_baidu_news_html = None  # deprecated, use app.services.collector instead


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

        if not source_ids:
            sources = WatchSourceRepository.get_enabled()
            source_ids = [str(s["id"]) for s in sources]

        all_news = []
        collect_results = []

        for sid in source_ids:
            try:
                sid = int(sid)
            except (ValueError, TypeError):
                continue
            source = WatchSourceRepository.get_by_id(sid)
            if not source or source["is_enabled"] == 0:
                continue

            # 构建请求 URL（教学视频方式: 用 {keyword}/{page} 模板参数）
            url_template = source["url_template"]
            encoded_kw = urllib.parse.quote(keyword)
            request_url = url_template.replace("{keyword}", encoded_kw).replace("{page}", "0")

            # 获取请求头并过滤不需要的字段
            raw_headers = WatchSourceRepository.get_headers(sid)
            headers = {
                k: v for k, v in raw_headers.items()
                if k.lower() not in (
                    "accept-encoding", "host",
                    "sec-fetch-dest", "sec-fetch-mode",
                    "sec-fetch-site", "sec-fetch-user",
                    "connection", "cache-control",
                )
            }

            # 调用采集服务（教学视频架构: services/collector）
            # 根据 URL 自动选择解析器
            if "sogou" in request_url.lower():
                parser = "sogou_news"
            else:
                parser = "baidu_news"
            status, size, text, parsed_news = fetch_and_parse(
                request_url, headers=headers, parser=parser,
            )

            if parsed_news:
                for news in parsed_news:
                    news_link = news.get("link", "")
                    result_id, is_new = WatchResultRepository.create_if_not_exists(
                        source_id=sid,
                        keyword=keyword,
                        request_url=news_link or request_url,
                        response_status=status,
                        response_size=len(news.get("summary", "")),
                        result_data=json.dumps(news, ensure_ascii=False),
                    )
                    if is_new:
                        all_news.append({
                            "id": result_id,
                            "title": news.get("title", ""),
                            "link": news_link,
                            "summary": news.get("summary", ""),
                            "source_name": news.get("source_name", source["name"]),
                        })
                collect_results.append({
                    "source_name": source["name"],
                    "status": status,
                    "news_count": len(parsed_news),
                })
            else:
                result_id, is_new = WatchResultRepository.create_if_not_exists(
                    source_id=sid,
                    keyword=keyword,
                    request_url=request_url,
                    response_status=status,
                    response_size=size,
                    result_data=text[:10000] if len(text) > 10000 else text,
                )
                collect_results.append({
                    "source_name": source["name"],
                    "status": status,
                    "size": size,
                    "id": result_id,
                })

        self.write({
            "code": 0,
            "msg": f"采集完成，共获取 {len(all_news)} 条新闻",
            "news": all_news,
            "results": collect_results,
            "total": len(all_news),
        })


class WatchSaveHandler(AdminBaseHandler):
    """保存选中的采集结果到数据仓库（含 URL 去重，v0.2.13 同时写入独立 data_warehouse 表）"""

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
        # 原有标记逻辑
        saved, skipped = WatchResultRepository.mark_saved_batch(ids)

        # v0.2.13: 同时写入独立 data_warehouse 表（借鉴郭家琪）
        dw_count = 0
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

        if dw_count > 0:
            msg = f"成功保存 {dw_count} 条结果到数据仓库"
            if skipped > 0:
                msg += f"（跳过 {skipped} 条重复/已保存）"
        else:
            msg = f"所有 {skipped} 条结果已存在或已保存，无需重复操作"

        self.write({"code": 0, "msg": msg})


class WatchDeepCollectHandler(AdminBaseHandler):
    """瞭望采集页一站式深度采集（v0.2.5 新增）

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

        # 步骤1：标记 watch_results 为已保存 + 写入 data_warehouse
        WatchResultRepository.mark_saved_batch(ids)

        saved_dw_ids = []
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
                                saved_dw_ids.append(new_row["id"])
                        except Exception as e:
                            logger.error(f"深度采集: 插入数据仓库记录失败 (rid={rid}): {e}", exc_info=True)
            conn.commit()

        if not saved_dw_ids:
            self.write({"code": 1, "msg": "保存到数据仓库失败，请检查数据"})
            return

        # 步骤2：对每个已保存的仓库记录执行深度采集
        from app.services.deep_collector import deep_fetch_and_save

        success_count = 0
        fail_count = 0
        already_count = 0
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        try:
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
                    executor, deep_fetch_and_save, dw_id, record["link"]
                )
                if success:
                    success_count += 1
                else:
                    fail_count += 1
        finally:
            executor.shutdown(wait=False)

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
