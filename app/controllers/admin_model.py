"""
admin_model.py — 模型引擎控制器

管理 AI 模型配置（多 Provider、多分类、参数设置）。
支持：列表/新增/编辑/删除/启停/清零/设为默认。

注：AI 对话功能已统一迁移至前台 /chat 页面（MCP 架构），
    后台 /admin/model/chat 已废弃。
"""
import json
import logging
import tornado.web
from app.controllers.admin_base import AdminBaseHandler
from app.models.ai_model import AiModelRepository, CATEGORIES, PROVIDERS

logger = logging.getLogger(__name__)


class ModelListHandler(AdminBaseHandler):
    """模型引擎列表页"""

    @tornado.web.authenticated
    def get(self):
        try:
            page = int(self.get_query_argument("page", 1))
        except (ValueError, TypeError):
            page = 1
        category = self.get_query_argument("category", "").strip()
        rows, total = AiModelRepository.get_all(page=page, page_size=6, category=category)
        total_pages = max(1, (total + 6 - 1) // 6)
        stats = AiModelRepository.get_stats()

        self.render(
            "admin/model_list.html",
            title="模型引擎 — 瞭望与问数系统",
            username=self.current_user,
            models=rows,
            page=page,
            total=total,
            total_pages=total_pages,
            category=category,
            categories=CATEGORIES,
            stats=stats,
            xsrf_token=self.xsrf_token.decode() if isinstance(self.xsrf_token, bytes) else self.xsrf_token,
        )


class ModelFormHandler(AdminBaseHandler):
    """模型引擎新增/编辑表单"""

    @tornado.web.authenticated
    def get(self):
        model_id = self.get_query_argument("id", None)
        model = None
        if model_id:
            try:
                model = AiModelRepository.get_by_id(int(model_id))
            except (ValueError, TypeError):
                self.write('<script>alert("无效的模型ID");window.history.back();</script>')
                return
            if not model:
                self.write('<script>alert("模型不存在");window.history.back();</script>')
                return

        self.render(
            "admin/model_form.html",
            title="编辑模型" if model else "新增模型",
            username=self.current_user,
            model=model,
            providers=PROVIDERS,
            categories=CATEGORIES,
        )

    @tornado.web.authenticated
    def post(self):
        model_id = self.get_body_argument("id", None)
        name = self.get_body_argument("name", "").strip()
        provider = self.get_body_argument("provider", "openai").strip()
        api_base = self.get_body_argument("api_base", "").strip()
        api_key = self.get_body_argument("api_key", "").strip()
        model_name = self.get_body_argument("model_name", "").strip()
        category = self.get_body_argument("category", "text").strip()
        system_prompt = self.get_body_argument("system_prompt", "").strip()
        try:
            temperature = float(self.get_body_argument("temperature", 0.7))
            top_p = float(self.get_body_argument("top_p", 1.0))
            top_k = int(self.get_body_argument("top_k", 50))
            max_tokens = int(self.get_body_argument("max_tokens", 4096))
            context_size = int(self.get_body_argument("context_size", 8192))
        except (ValueError, TypeError):
            self.write('<script>alert("参数值格式不正确，请检查数字字段");window.history.back();</script>')
            return

        if not name:
            self.write('<script>alert("模型名称不能为空");window.history.back();</script>')
            return

        if model_id:
            try:
                model_id = int(model_id)
            except (ValueError, TypeError):
                self.write('<script>alert("无效的模型ID");window.history.back();</script>')
                return
            # 检查是否需要清除 API Key（管理员主动勾选"清除密钥"复选框）
            clear_key = self.get_body_argument("clear_key", "0") == "1"
            if clear_key:
                api_key = ""  # 明确清除
            elif not api_key:
                # 编辑时：如果 API Key 未填写且未勾选清除，保留数据库中的旧值
                existing = AiModelRepository.get_by_id(model_id)
                if existing:
                    api_key = existing["api_key"]
            ok = AiModelRepository.update(
                model_id, name, provider, api_base, api_key, model_name,
                category, system_prompt, temperature, top_p, top_k, max_tokens, context_size
            )
            msg = "更新成功" if ok else "更新失败"
        else:
            new_id = AiModelRepository.create(
                name, provider, api_base, api_key, model_name,
                category, system_prompt, temperature, top_p, top_k, max_tokens, context_size
            )
            msg = "创建成功" if new_id > 0 else "创建失败"

        self.redirect(f"/admin/model?msg={msg}")


class ModelDeleteHandler(AdminBaseHandler):
    """删除模型"""

    @tornado.web.authenticated
    def post(self):
        try:
            model_id = int(self.get_body_argument("id", 0))
        except (ValueError, TypeError):
            self.write('<script>alert("无效的模型ID");window.history.back();</script>')
            return
        AiModelRepository.delete(model_id)
        self.redirect("/admin/model?msg=已删除")


class ModelToggleHandler(AdminBaseHandler):
    """启用/禁用模型"""

    @tornado.web.authenticated
    def post(self):
        try:
            model_id = int(self.get_body_argument("id", 0))
        except (ValueError, TypeError):
            self.write('<script>alert("无效的模型ID");window.history.back();</script>')
            return
        status = AiModelRepository.toggle_enabled(model_id)
        if status == -1:
            self.write('<script>alert("模型不存在");window.history.back();</script>')
        else:
            self.redirect(
                f"/admin/model?msg={'已启用' if status == 1 else '已禁用'}"
            )


class ModelDefaultHandler(AdminBaseHandler):
    """设为默认模型"""

    @tornado.web.authenticated
    def post(self):
        try:
            model_id = int(self.get_body_argument("id", 0))
        except (ValueError, TypeError):
            self.write('<script>alert("无效的模型ID");window.history.back();</script>')
            return
        AiModelRepository.set_default(model_id)
        self.redirect("/admin/model?msg=已设为默认模型")


class ModelApiListHandler(AdminBaseHandler):
    """API: 模型列表 JSON（供前端 AJAX 调用，仅返回已启用的模型）"""

    @tornado.web.authenticated
    def get(self):
        try:
            page = int(self.get_query_argument("page", 1))
        except (ValueError, TypeError):
            page = 1
        try:
            limit = int(self.get_query_argument("limit", 6))
        except (ValueError, TypeError):
            limit = 6
        category = self.get_query_argument("category", "").strip()
        rows, total = AiModelRepository.get_all(
            page=page, page_size=limit, category=category, enabled_only=True
        )
        items = []
        for r in rows:
            items.append({
                "id": r["id"],
                "name": r["name"],
                "provider": r["provider"],
                "model_name": r["model_name"],
                "category": r["category"],
                "is_default": r["is_default"],
                "is_enabled": r["is_enabled"],
                "has_key": bool(r["api_key"]),
            })
        self.write({"code": 0, "total": total, "items": items})



