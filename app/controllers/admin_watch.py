"""
admin_watch.py — 瞭望采集控制器

A区: 搜索框 + 采集按钮（居中）
B区: 瞭望源规则列表（含参数配置）
C区: 采集结果展示区（百度新闻解析 + 全选/保存到数据仓库）

采集服务委托给 app.services.collector（按教学视频架构）。
"""
import json
import urllib.parse
import tornado.web
from app.controllers.admin_base import AdminBaseHandler
from app.models.watch_source import WatchSourceRepository
from app.models.watch_result import WatchResultRepository
from app.models.data_warehouse import DataWarehouseRepository
from app.services.collector import fetch_and_parse


# 向后兼容别名
parse_baidu_news_html = None  # deprecated, use app.services.collector instead


class WatchHandler(AdminBaseHandler):
    """瞭望采集主页面"""

    @tornado.web.authenticated
    def get(self):
        keyword = self.get_query_argument("keyword", "").strip()
        page = int(self.get_query_argument("page", 1))
        source_id = self.get_query_argument("source_id", None)
        if source_id:
            source_id = int(source_id)

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
        source_ids_raw = self.get_body_argument("source_ids", "")
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
                    result_id = WatchResultRepository.create(
                        source_id=sid,
                        keyword=keyword,
                        request_url=news.get("link", request_url),
                        response_status=status,
                        response_size=len(news.get("summary", "")),
                        result_data=json.dumps(news, ensure_ascii=False),
                    )
                    all_news.append({
                        "id": result_id,
                        "title": news.get("title", ""),
                        "link": news.get("link", ""),
                        "summary": news.get("summary", ""),
                        "source_name": news.get("source_name", source["name"]),
                    })
                collect_results.append({
                    "source_name": source["name"],
                    "status": status,
                    "news_count": len(parsed_news),
                })
            else:
                result_id = WatchResultRepository.create(
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
        result_ids = self.get_body_arguments("result_ids")
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

        if saved > 0 or dw_count > 0:
            msg = f"成功保存 {saved} 条结果到数据仓库"
            if skipped > 0:
                msg += f"（跳过 {skipped} 条重复/已保存）"
        else:
            msg = f"所有 {skipped} 条结果已存在或已保存，无需重复操作"

        self.write({"code": 0, "msg": msg})
