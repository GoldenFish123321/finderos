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

from app.models.watch_source import WatchSourceRepository, resolve_source_parser
from app.models.watch_result import WatchResultRepository
from app.models.data_warehouse import DataWarehouseRepository
from app.services.collector import fetch_and_parse_via_handler
from app.utils.security import write_audit_log

logger = logging.getLogger(__name__)


class SentimentScanner:
    """定时舆情扫描器：定期扫描数据仓库和对话中的敏感词。"""

    def __init__(self, check_interval_ms: int = 300000):
        """
        :param check_interval_ms: 扫描间隔（毫秒），默认 5 分钟
        """
        self._check_interval_ms = check_interval_ms
        self._callback = None
        self._running = False
        self._executor = None
        self._scan_future = None

    def start(self):
        if self._running:
            return
        if self._executor is None:
            self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="sentiment")
        self._running = True
        self._callback = PeriodicCallback(self._tick, self._check_interval_ms)
        self._callback.start()
        logger.info(f"舆情扫描器已启动（间隔: {self._check_interval_ms // 1000}s）")

    def stop(self):
        self._running = False
        if self._callback:
            self._callback.stop()
            self._callback = None
        if self._executor:
            self._executor.shutdown(wait=False)
            self._executor = None

    def _tick(self):
        if self._scan_future and not self._scan_future.done():
            logger.info("舆情扫描上一轮尚未完成，跳过本次 tick")
            return
        self._scan_future = self._executor.submit(self._run_scan)

    @staticmethod
    def _run_scan():
        try:
            from app.services.system_operations import backup_database_if_due
            backup_database_if_due()
            from app.models.sensitive_word import SensitiveWordRepository
            result = SensitiveWordRepository.scan_all()
            if result["total"] > 0:
                from app.services.system_operations import send_alert_notification
                send_alert_notification(result["total"])
                logger.info(f"舆情扫描: 发现 {result['total']} 条新预警 "
                           f"(仓库 {result['warehouse']}, 对话 {result['conversation']})")
            # 对未分析的预警执行 AI 语义分析（每次最多分析 5 条）
            try:
                analyzed = SensitiveWordRepository.analyze_pending_alerts(limit=5)
                if analyzed:
                    logger.info(f"AI 风析: 完成 {len(analyzed)} 条预警语义分析")
            except Exception as ae:
                logger.warning(f"AI 风析异常（不影响扫描）: {ae}")
        except Exception as e:
            logger.error(f"舆情扫描异常: {e}")


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
        self._executor = None

    def start(self):
        """启动调度器。"""
        if self._running:
            return
        if self._executor is None:
            self._executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=2, thread_name_prefix="scheduler"
            )
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
        if self._executor:
            self._executor.shutdown(wait=False)
            self._executor = None
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
        """对单个瞭望源执行采集（通过统一出口 fetch_and_parse_via_handler）。"""
        source_id = source["id"]
        name = source.get("name", "unknown")
        url_template = source.get("url_template", "")

        if not url_template:
            return

        # 使用配置化的关键词（从环境变量或默认值读取）
        from app.config.settings import settings
        keywords = settings.SCHEDULED_COLLECT_KEYWORDS
        parser = resolve_source_parser(source)

        try:
            import json

            total_collected = 0
            for keyword in keywords:
                try:
                    status, size, text, parsed_news = fetch_and_parse_via_handler(
                        source_id=source_id, keyword=keyword, page=0,
                        parser=parser, timeout=20,
                    )
                    for news in parsed_news:
                        link = news.get("link", "")
                        result_id, is_new = WatchResultRepository.create_if_not_exists(
                            source_id=source_id,
                            keyword=keyword,
                            request_url=link or url_template,
                            response_status=status,
                            response_size=size,
                            result_data=json.dumps(news, ensure_ascii=False),
                        )
                        if is_new:
                            total_collected += 1
                        # 自动保存到数据仓库（与 MCP 采集工具行为一致）
                        if result_id > 0:
                            DataWarehouseRepository.create(
                                result_id=result_id,
                                title=news.get("title", ""),
                                link=link or url_template,
                                summary=news.get("summary", "") or "",
                                source_name=news.get("source_name", name),
                                raw_data=json.dumps(news, ensure_ascii=False),
                            )
                            # 标记 watch_results 为已保存
                            WatchResultRepository.mark_saved(result_id)
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
