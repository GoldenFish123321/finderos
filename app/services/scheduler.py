"""
scheduler.py — 定时采集调度器

基于 Tornado PeriodicCallback 实现的轻量级定时任务调度。
零额外依赖，符合项目设计理念。
"""
import concurrent.futures
import logging
import threading
import time
from tornado.ioloop import PeriodicCallback

from app.models.watch_source import WatchSourceRepository
from app.models.watch_result import WatchResultRepository
from app.models.data_warehouse import DataWarehouseRepository
from app.services.collector import fetch_and_parse
from app.utils.security import write_audit_log, validate_url_safe

logger = logging.getLogger(__name__)


class CollectionScheduler:
    """定时采集调度器：按配置的间隔自动执行瞭望采集任务。"""

    def __init__(self, app, check_interval_ms: int = 60000):
        """
        初始化调度器。
        :param app: Tornado Application 实例
        :param check_interval_ms: 检查间隔（毫秒），默认 60 秒
        """
        self._app = app
        self._check_interval_ms = check_interval_ms
        self._callback = None
        self._lock = threading.Lock()
        self._last_run: dict[int, float] = {}  # source_id → 上次执行时间戳
        self._running = False
        # 专用线程池，避免阻塞 IOLoop
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="scheduler")

    def start(self):
        """启动调度器。"""
        if self._running:
            return
        self._running = True
        self._callback = PeriodicCallback(self._tick, self._check_interval_ms)
        self._callback.start()
        logger.info(f"定时采集调度器已启动（检查间隔: {self._check_interval_ms // 1000}s）")

    def stop(self):
        """停止调度器。"""
        self._running = False
        if self._callback:
            self._callback.stop()
            self._callback = None
        self._executor.shutdown(wait=False)
        logger.info("定时采集调度器已停止")

    def _tick(self):
        """每次 tick 执行：检查是否需要采集某个瞭望源。"""
        try:
            sources = WatchSourceRepository.get_all_enabled()
            now = time.time()

            for source in sources:
                interval_minutes = source.get("schedule_interval", 0) or 0
                if interval_minutes <= 0:
                    continue  # 未配置定时采集

                source_id = source["id"]
                last_run = self._last_run.get(source_id, 0)
                interval_seconds = interval_minutes * 60

                if now - last_run < interval_seconds:
                    continue  # 还没到下次执行时间

                # 执行采集
                with self._lock:
                    self._last_run[source_id] = now

                # 在线程池中执行采集，避免阻塞 IOLoop
                self._executor.submit(self._collect_source, source)

        except Exception as e:
            logger.error(f"定时采集调度器 tick 异常: {e}")

    def _collect_source(self, source: dict):
        """对单个瞭望源执行采集。"""
        source_id = source["id"]
        name = source.get("name", "unknown")
        url_template = source.get("url_template", "")
        request_headers_str = source.get("request_headers", "{}")

        if not url_template:
            return

        # 使用配置化的关键词（从环境变量或默认值读取）
        from app.config.settings import settings
        keywords = settings.SCHEDULED_COLLECT_KEYWORDS
        parser = "baidu_news"
        if "sogou" in url_template.lower():
            parser = "sogou_news"

        try:
            import json
            import urllib.parse
            headers = json.loads(request_headers_str) if request_headers_str else {}

            total_collected = 0
            for keyword in keywords:
                encoded_kw = urllib.parse.quote(keyword, encoding="utf-8")
                request_url = url_template.replace("{keyword}", encoded_kw).replace("{page}", "0")

                safe, reason = validate_url_safe(request_url)
                if not safe:
                    logger.warning(f"定时采集 SSRF 拦截: {request_url}, reason={reason}")
                    continue

                try:
                    status, size, text, parsed_news = fetch_and_parse(
                        request_url, headers, parser, timeout=20
                    )
                    for news in parsed_news:
                        link = news.get("link", "")
                        # request_url 优先存新闻链接（用于去重），空则回退到搜索URL
                        result_id, is_new = WatchResultRepository.create_if_not_exists(
                            source_id=source_id,
                            keyword=keyword,
                            request_url=link or request_url,
                            response_status=status,
                            response_size=size,
                            result_data=json.dumps(news, ensure_ascii=False),
                        )
                        if is_new:
                            total_collected += 1
                except Exception as e:
                    logger.warning(f"定时采集 {name}: 关键词'{keyword}' 采集失败: {e}")

            if total_collected > 0:
                logger.info(f"定时采集 {name}: 采集到 {total_collected} 条新数据")
                write_audit_log(
                    action="SCHEDULED_COLLECT",
                    username="scheduler",
                    target=f"source:{source_id}",
                    detail=f"collected={total_collected}, keywords={keywords}",
                    client_ip="127.0.0.1",
                )

        except Exception as e:
            logger.error(f"定时采集 {name} 异常: {e}")
