"""Configured database backup and notification operations."""
from datetime import datetime
import json
import logging
import os
import sqlite3

from app.config.settings import settings
from app.utils.safe_http import safe_http_request

logger = logging.getLogger(__name__)


def backup_database_if_due(now: float | None = None) -> str | None:
    source = os.path.abspath(settings.DB_PATH)
    target_dir = os.path.abspath(settings.DB_BACKUP_PATH)
    os.makedirs(target_dir, exist_ok=True)
    backups = sorted(
        (os.path.join(target_dir, name) for name in os.listdir(target_dir) if name.startswith("finderos-") and name.endswith(".db")),
        key=os.path.getmtime,
    )
    timestamp = now if now is not None else datetime.now().timestamp()
    if backups and timestamp - os.path.getmtime(backups[-1]) < settings.DB_BACKUP_INTERVAL_DAYS * 86400:
        return None
    target = os.path.join(target_dir, datetime.fromtimestamp(timestamp).strftime("finderos-%Y%m%d-%H%M%S.db"))
    try:
        with sqlite3.connect(source) as source_conn, sqlite3.connect(target) as target_conn:
            source_conn.backup(target_conn)
        for old in backups[:max(0, len(backups) + 1 - settings.DB_BACKUP_KEEP_COUNT)]:
            os.remove(old)
        return target
    except Exception as exc:
        logger.warning("Configured database backup failed: %s", exc)
        return None


def send_alert_notification(total: int) -> bool:
    if not settings.WEBHOOK_URL or total <= 0:
        return False
    payload = json.dumps({"event": "sentiment_alerts", "count": int(total)}).encode("utf-8")
    try:
        response = safe_http_request(
            settings.WEBHOOK_URL, method="POST",
            headers={"Content-Type": "application/json"}, body=payload,
            timeout=10, max_bytes=64 * 1024,
        )
        return 200 <= response.status < 300
    except Exception as exc:
        logger.warning("Configured alert notification failed: %s", exc)
        return False
