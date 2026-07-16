"""
admin_config.py — 系统设置控制器

管理后台常规设置页面：系统名称/Logo/备案号/端口/AI默认参数。
支持 Logo 图片上传。
"""
import os
import time
import urllib.parse
import tornado.web
from app.config.settings import settings
from app.controllers.admin_base import AdminBaseHandler
from app.models.system_config import SystemConfigRepository
from app.models.ai_model import AiModelRepository
from app.utils.security import write_audit_log

# Logo 上传配置
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "uploads")
ALLOWED_LOGO_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
MAX_LOGO_SIZE = 2 * 1024 * 1024  # 2 MB
LOGO_FILE_PREFIX = "logo_"


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
        logo_path = None
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
                    try:
                        os.remove(old_path)
                    except Exception:
                        pass
            updates["system_logo"] = ""
            write_audit_log(
                action="SYSCONFIG_LOGO_REMOVE",
                username=self.current_user,
                target="system_config:system_logo",
                detail="Logo removed",
                client_ip=self.request.remote_ip or "",
            )

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

                if len(file_obj.get("body", b"")) > MAX_LOGO_SIZE:
                    self.redirect("/admin/config?error=" + urllib.parse.quote(
                        "图片大小不能超过 2MB"))
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
                self._cleanup_old_logos(new_filename)

                write_audit_log(
                    action="SYSCONFIG_LOGO_UPLOAD",
                    username=self.current_user,
                    target="system_config:system_logo",
                    detail=f"Logo uploaded: {new_filename}",
                    client_ip=self.request.remote_ip or "",
                )
        except Exception as e:
            self.redirect("/admin/config?error=" + urllib.parse.quote(f"Logo 上传失败：{e}"))
            return

        # 2. 读取文本配置项
        updates = {}
        for key in (
            "system_name", "system_subtitle", "icp_number", "default_port",
            "ai_default_model", "ai_default_temperature", "ai_default_max_tokens",
        ):
            val = self.get_body_argument(key, None)
            if val is not None:
                updates[key] = val.strip()

        # Logo 路径单独处理（仅当有上传时更新）
        if logo_path:
            updates["system_logo"] = logo_path

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
                self.redirect("/admin/config?error=" + urllib.parse.quote("保存失败，请重试"))
                return

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
        except Exception:
            pass  # 清理失败不影响主流程
