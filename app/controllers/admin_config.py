"""
admin_config.py — 系统设置控制器

管理后台常规设置页面：系统名称/Logo/备案号/端口/AI默认参数。
支持 Logo 图片上传。
"""
import os
import time
import urllib.parse
import logging
import tornado.web
from app.config.settings import settings
from app.controllers.admin_base import AdminBaseHandler
from app.models.system_config import SystemConfigRepository
from app.models.ai_model import AiModelRepository
from app.utils.security import write_audit_log

# Logo 上传配置
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "uploads")
ALLOWED_LOGO_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
LOGO_FILE_PREFIX = "logo_"
logger = logging.getLogger(__name__)

_INTEGER_LIMITS = {
    "default_port": (1, 65535), "ai_default_max_tokens": (1, 131072),
    "backup_interval_days": (1, 365), "backup_retention": (1, 365),
    "default_collection_interval": (10, 86400),
    "session_expiry_minutes": (5, 525600), "max_upload_mb": (1, 1024),
}


def validate_config_updates(updates: dict[str, str]) -> None:
    """Reject values that the runtime cannot safely apply before persisting them."""
    for key, (low, high) in _INTEGER_LIMITS.items():
        if key in updates:
            try:
                value = int(updates[key])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{key} 必须是整数") from exc
            if not low <= value <= high:
                raise ValueError(f"{key} 必须在 {low} 到 {high} 之间")
    if "ai_default_temperature" in updates:
        try:
            temperature = float(updates["ai_default_temperature"])
        except (TypeError, ValueError) as exc:
            raise ValueError("ai_default_temperature 必须是数字") from exc
        if not 0 <= temperature <= 2:
            raise ValueError("ai_default_temperature 必须在 0 到 2 之间")
    if updates.get("log_level", "INFO").upper() not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ValueError("log_level 无效")
    if updates.get("registration_enabled", "true").lower() not in {"true", "false"}:
        raise ValueError("registration_enabled 无效")
    webhook = updates.get("notification_webhook", "")
    if webhook and urllib.parse.urlparse(webhook).scheme not in {"http", "https"}:
        raise ValueError("notification_webhook 必须是 HTTP 或 HTTPS 地址")


class SystemConfigHandler(AdminBaseHandler):
    """系统常规设置页面（GET 渲染 / POST 保存）"""

    @tornado.web.authenticated
    def get(self):
        configs = SystemConfigRepository.get_all()
        # 分组：general / ai
        general_configs = [c for c in configs if c["category"] == "general"]
        ai_configs = [c for c in configs if c["category"] == "ai"]
        # 构造 key→value 查找字典
        config_dict = {c["key"]: c for c in configs}
        # 加载已启用的 AI 模型列表供下拉选择
        enabled_models, _ = AiModelRepository.get_all(page=1, page_size=999, enabled_only=True)

        # 从 URL 获取操作反馈消息
        msg = self.get_query_argument("msg", "")
        error = self.get_query_argument("error", "")

        self.render(
            "admin/config.html",
            title=f"常规设置 — {settings.SYSTEM_NAME}",
            username=self.current_user,
            general_configs=general_configs,
            ai_configs=ai_configs,
            config_dict=config_dict,
            enabled_models=enabled_models,
            feedback_msg=msg,
            feedback_error=error,
        )

    @tornado.web.authenticated
    def post(self):
        # 1. 处理 Logo 操作
        updates = {}
        logo_path = None
        old_logo_path = None
        new_filename = None
        remove_logo = self.get_body_argument("remove_logo", "0")

        # 1a. 移除 Logo
        if remove_logo == "1":
            old_logo = SystemConfigRepository.get_by_key("system_logo")
            if old_logo and old_logo.get("value"):
                old_path = os.path.join(
                    os.path.dirname(os.path.dirname(__file__)),
                    old_logo["value"].lstrip("/")
                )
                if os.path.isfile(old_path):
                    old_logo_path = old_path
            updates["system_logo"] = ""

        # 1b. 上传新 Logo
        try:
            files = self.request.files
            if "logo_file" in files and files["logo_file"]:
                file_obj = files["logo_file"][0]
                filename = file_obj.get("filename", "")
                ext = os.path.splitext(filename)[1].lower()

                if ext not in ALLOWED_LOGO_EXTENSIONS:
                    self.redirect("/admin/config?error=" + urllib.parse.quote(
                        "不支持的图片格式，仅允许：png/jpg/jpeg/gif/webp/svg"))
                    return

                max_logo_size = settings.MAX_UPLOAD_MB * 1024 * 1024
                if len(file_obj.get("body", b"")) > max_logo_size:
                    self.redirect("/admin/config?error=" + urllib.parse.quote(
                        f"图片大小不能超过 {settings.MAX_UPLOAD_MB}MB"))
                    return

                # 确保上传目录存在
                os.makedirs(UPLOAD_DIR, exist_ok=True)

                # 生成唯一文件名：logo_{timestamp}.{ext}
                new_filename = f"{LOGO_FILE_PREFIX}{int(time.time() * 1000)}{ext}"
                filepath = os.path.join(UPLOAD_DIR, new_filename)

                with open(filepath, "wb") as f:
                    f.write(file_obj["body"])

                # 相对路径（前端通过 /static/uploads/... 访问）
                logo_path = f"/static/uploads/{new_filename}"

                # 清理旧 Logo 文件
        except Exception as e:
            logger.exception("Logo upload failed")
            self.redirect("/admin/config?error=" + urllib.parse.quote("Logo 上传失败，请检查文件后重试"))
            return

        # 2. 读取文本配置项
        for key in (
            "system_name", "system_subtitle", "icp_number", "default_port",
            "ai_default_model", "ai_default_temperature", "ai_default_max_tokens",
            "backup_path", "backup_interval_days", "backup_retention", "log_level",
            "notification_webhook", "default_collection_interval", "registration_enabled",
            "session_expiry_minutes", "max_upload_mb",
        ):
            val = self.get_body_argument(key, None)
            if val is not None:
                updates[key] = val.strip()

        # Logo 路径单独处理（仅当有上传时更新）
        if logo_path:
            updates["system_logo"] = logo_path

        try:
            validate_config_updates(updates)
        except ValueError as e:
            if logo_path:
                try:
                    os.remove(filepath)
                except OSError:
                    pass
            self.redirect("/admin/config?error=" + urllib.parse.quote(str(e)))
            return

        if updates:
            count = SystemConfigRepository.bulk_update(updates)
            if count >= 0:
                # 立即刷新内存中的 settings，使模板渲染即时生效
                settings.load_from_db()
                write_audit_log(
                    action="SYSCONFIG_UPDATE",
                    username=self.current_user,
                    target="system_config",
                    detail=f"updated {count} keys: {', '.join(updates.keys())}",
                    client_ip=self.request.remote_ip or "",
                )
            else:
                if logo_path:
                    try:
                        os.remove(filepath)
                    except OSError as e:
                        logger.warning("Failed to remove uncommitted logo %s: %s", filepath, e)
                self.redirect("/admin/config?error=" + urllib.parse.quote("保存失败，请重试"))
                return

        if remove_logo == "1" and old_logo_path:
            try:
                os.remove(old_logo_path)
            except OSError as e:
                logger.warning("Failed to remove old logo %s: %s", old_logo_path, e)
        if new_filename:
            self._cleanup_old_logos(new_filename)
        if remove_logo == "1" or new_filename:
            write_audit_log(
                action="SYSCONFIG_LOGO_UPLOAD" if new_filename else "SYSCONFIG_LOGO_REMOVE",
                username=self.current_user,
                target="system_config:system_logo",
                detail=f"Logo uploaded: {new_filename}" if new_filename else "Logo removed",
                client_ip=self.request.remote_ip or "",
            )

        self.redirect("/admin/config?msg=保存成功")

    @staticmethod
    def _cleanup_old_logos(current_filename: str):
        """删除旧的 Logo 文件（根据文件名前缀匹配），保留当前文件。"""
        try:
            if not os.path.isdir(UPLOAD_DIR):
                return
            for fname in os.listdir(UPLOAD_DIR):
                if fname.startswith(LOGO_FILE_PREFIX) and fname != current_filename:
                    fpath = os.path.join(UPLOAD_DIR, fname)
                    if os.path.isfile(fpath):
                        os.remove(fpath)
        except Exception as e:
            logger.warning("Failed to clean old logos in %s: %s", UPLOAD_DIR, e)
