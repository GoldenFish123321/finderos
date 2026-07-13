"""
admin_model.py — 模型引擎控制器

管理 AI 模型配置（多 Provider、多分类、参数设置）。
支持：列表/新增/编辑/删除/启停/清零/设为默认。
"""
import json
import tornado.web
from app.controllers.admin_base import AdminBaseHandler
from app.models.ai_model import AiModelRepository, CATEGORIES, PROVIDERS


class ModelListHandler(AdminBaseHandler):
    """模型引擎列表页"""

    @tornado.web.authenticated
    def get(self):
        page = int(self.get_query_argument("page", 1))
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
        )


class ModelFormHandler(AdminBaseHandler):
    """模型引擎新增/编辑表单"""

    @tornado.web.authenticated
    def get(self):
        model_id = self.get_query_argument("id", None)
        model = None
        if model_id:
            model = AiModelRepository.get_by_id(int(model_id))
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
        temperature = float(self.get_body_argument("temperature", 0.7))
        top_p = float(self.get_body_argument("top_p", 1.0))
        top_k = int(self.get_body_argument("top_k", 50))
        max_tokens = int(self.get_body_argument("max_tokens", 4096))
        context_size = int(self.get_body_argument("context_size", 8192))

        if not name:
            self.write('<script>alert("模型名称不能为空");window.history.back();</script>')
            return

        if model_id:
            ok = AiModelRepository.update(
                int(model_id), name, provider, api_base, api_key, model_name,
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
        model_id = int(self.get_body_argument("id", 0))
        AiModelRepository.delete(model_id)
        self.redirect("/admin/model?msg=已删除")


class ModelToggleHandler(AdminBaseHandler):
    """启用/禁用模型"""

    @tornado.web.authenticated
    def post(self):
        model_id = int(self.get_body_argument("id", 0))
        status = AiModelRepository.toggle_enabled(model_id)
        self.redirect(
            f"/admin/model?msg={'已启用' if status == 1 else '已禁用'}"
        )


class ModelDefaultHandler(AdminBaseHandler):
    """设为默认模型"""

    @tornado.web.authenticated
    def post(self):
        model_id = int(self.get_body_argument("id", 0))
        AiModelRepository.set_default(model_id)
        self.redirect("/admin/model?msg=已设为默认模型")


class ModelApiListHandler(AdminBaseHandler):
    """API: 模型列表 JSON（供前端 AJAX 调用）"""

    @tornado.web.authenticated
    def get(self):
        page = int(self.get_query_argument("page", 1))
        limit = int(self.get_query_argument("limit", 6))
        category = self.get_query_argument("category", "").strip()
        rows, total = AiModelRepository.get_all(page=page, page_size=limit, category=category)
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


class ModelChatHandler(AdminBaseHandler):
    """模型对话 — SSE 流式响应"""

    @tornado.web.authenticated
    async def post(self):
        model_id = int(self.get_body_argument("model_id", 0))
        message = self.get_body_argument("message", "").strip()

        if not message:
            self.write({"code": 1, "msg": "消息不能为空"})
            return

        model = AiModelRepository.get_by_id(model_id)
        if not model or model["is_enabled"] == 0:
            self.write({"code": 1, "msg": "模型不可用"})
            return

        api_base = (model["api_base"] or "https://api.openai.com/v1").rstrip("/")
        api_key = model["api_key"] or ""
        model_name = model["model_name"] or model["name"]
        system_prompt = model["system_prompt"] or ""
        temperature = model["temperature"]
        max_tokens = model["max_tokens"]

        # 构建消息
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": message})

        payload = json.dumps({
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }).encode()

        # SSE 流式代理
        self.set_header("Content-Type", "text/event-stream")
        self.set_header("Cache-Control", "no-cache")
        self.set_header("Connection", "keep-alive")
        self.set_header("X-Accel-Buffering", "no")

        import urllib.request
        try:
            req = urllib.request.Request(
                f"{api_base}/chat/completions",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                }
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                total_tokens = 0
                content_chars = 0
                for line in resp:
                    line = line.decode("utf-8", errors="replace").strip()
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            self.write(f"data: [DONE]\n\n")
                            await self.flush()
                            break
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                content_chars += len(content)
                                self.write(f"data: {json.dumps({'content': content})}\n\n")
                                await self.flush()
                            # 优先从 usage 获取，否则从 finish_reason 推断
                            if "usage" in chunk and chunk["usage"]:
                                total_tokens = chunk["usage"].get("total_tokens", 0)
                        except json.JSONDecodeError:
                            pass
                # 发送 token 统计（API 返回的精确值或估算值）
                if total_tokens == 0 and content_chars > 0:
                    total_tokens = max(1, content_chars // 2)  # 估算：中文约2字符/token
                self.write(f"event: stats\ndata: {json.dumps({'tokens': total_tokens})}\n\n")
                await self.flush()
        except Exception as e:
            self.write(f"data: {json.dumps({'error': str(e)})}\n\n")
            await self.flush()


class ModelChatPageHandler(AdminBaseHandler):
    """模型对话测试页面"""

    @tornado.web.authenticated
    def get(self):
        model_id = self.get_query_argument("model_id", None)
        models_data, _ = AiModelRepository.get_all(page=1, page_size=50)

        selected_model = None
        if model_id:
            selected_model = AiModelRepository.get_by_id(int(model_id))

        self.render(
            "admin/model_chat.html",
            title="模型测试 — 瞭望与问数系统",
            username=self.current_user,
            models=models_data,
            selected=selected_model,
            xsrf_token=self.xsrf_token.decode() if isinstance(self.xsrf_token, bytes) else self.xsrf_token,
        )
