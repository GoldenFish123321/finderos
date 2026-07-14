"""
admin_model.py — 模型引擎控制器

管理 AI 模型配置（多 Provider、多分类、参数设置）。
支持：列表/新增/编辑/删除/启停/清零/设为默认。
支持：SSE 流式对话（真实 API + Token 追踪 + 本地 Mock 回退）。
"""
import asyncio
import atexit
import concurrent.futures
import json
import logging
import tornado.web
from app.controllers.admin_base import AdminBaseHandler
from app.models.ai_model import AiModelRepository, CATEGORIES, PROVIDERS
from app.models.conversation import ConversationRepository

logger = logging.getLogger(__name__)

# 全局线程池（复用，避免每个请求创建销毁）
_chat_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="chat")
atexit.register(_chat_executor.shutdown, wait=True)


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
            model_id = int(model_id)
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
        model_id = int(self.get_body_argument("id", 0))
        AiModelRepository.delete(model_id)
        self.redirect("/admin/model?msg=已删除")


class ModelToggleHandler(AdminBaseHandler):
    """启用/禁用模型"""

    @tornado.web.authenticated
    def post(self):
        model_id = int(self.get_body_argument("id", 0))
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
        model_id = int(self.get_body_argument("id", 0))
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


class ModelChatHandler(AdminBaseHandler):
    """模型对话 — SSE 流式响应（真实 API 调用 + 本地 Mock 回退 + Token 追踪）"""

    @tornado.web.authenticated
    async def post(self):
        try:
            model_id = int(self.get_body_argument("model_id", 0))
        except (ValueError, TypeError):
            self.write({"code": 1, "msg": "无效的模型ID"})
            return
        message = self.get_body_argument("message", "").strip()
        conversation_id = self.get_body_argument("conversation_id", None)

        if not message:
            self.write({"code": 1, "msg": "消息不能为空"})
            return
        if len(message) > 10000:
            self.write({"code": 1, "msg": "消息过长（最多10000字符）"})
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

        # 多轮对话：加载历史消息（含归属权校验，防止 IDOR 越权）
        history_messages = []
        conv_id = None
        if conversation_id:
            try:
                conv_id = int(conversation_id)
                conv = ConversationRepository.get_by_id(conv_id)
                if conv and conv.get("username", "") == self.current_user:
                    history_messages = ConversationRepository.get_recent_messages(conv_id, limit=10)
                else:
                    conv_id = None  # 无权访问，回退为单轮对话
            except (ValueError, TypeError):
                pass

        # 构建完整消息列表
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.extend(history_messages)
        messages.append({"role": "user", "content": message})

        # SSE 响应头
        self.set_header("Content-Type", "text/event-stream")
        self.set_header("Cache-Control", "no-cache")
        self.set_header("Connection", "keep-alive")
        self.set_header("X-Accel-Buffering", "no")

        total_tokens = 0
        api_success = False
        is_mock = True  # 默认使用 Mock，真实 API 成功时改为 False

        # 尝试真实 API 调用（在线程池中执行，避免阻塞 Tornado 事件循环）
        if api_key:
            # SSRF 防护：校验 API Base URL 安全性
            from app.utils.security import validate_url_safe
            safe, reason = validate_url_safe(api_base)
            if not safe:
                logger.warning(f"SSRF 拦截: api_base={api_base}, reason={reason}")
                self.write(f"data: {json.dumps({'error': f'API Base URL 不安全: {reason}'})}\n\n")
                await self.flush()
                self.write(f"event: stats\ndata: {json.dumps({'tokens': 0, 'mock': True})}\n\n")
                self.write(f"data: [DONE]\n\n")
                await self.flush()
                return

            payload = json.dumps({
                "model": model_name,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True,
            }).encode()

            def _sync_stream_call():
                """在线程池中执行的同步 HTTP 流式调用。
                在线程池内完成所有阻塞 I/O（resp.read），返回原始字节数据。
                返回 (raw_data, error)。"""
                import urllib.request
                import urllib.error

                try:
                    req = urllib.request.Request(
                        f"{api_base}/chat/completions",
                        data=payload,
                        headers={
                            "Content-Type": "application/json",
                            "Authorization": f"Bearer {api_key}",
                        },
                    )
                    with urllib.request.urlopen(req, timeout=120) as resp:
                        return resp.read(), None
                except Exception as e:
                    return b"", str(e)

            loop = asyncio.get_event_loop()
            raw_data, err = await loop.run_in_executor(_chat_executor, _sync_stream_call)

            if err is None:
                api_success = True
                is_mock = False
                content_chars = 0
                assistant_reply_parts = []
                for line in raw_data.split(b"\n"):
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
                                assistant_reply_parts.append(content)
                                self.write(
                                    f"data: {json.dumps({'content': content})}\n\n"
                                )
                                await self.flush()
                            if "usage" in chunk and chunk["usage"]:
                                total_tokens = chunk["usage"].get(
                                    "total_tokens", 0
                                )
                        except json.JSONDecodeError:
                            pass
                assistant_reply = "".join(assistant_reply_parts)
                if total_tokens == 0 and content_chars > 0:
                    total_tokens = max(1, content_chars // 2)
                # API 返回空响应：回退到 Mock，避免保存空消息污染对话历史
                if not assistant_reply:
                    logger.warning("API 返回空响应，回退到本地 Mock")
                    api_success = False
                    is_mock = True
            else:
                logger.warning(f"API 调用失败: {err}，回退到本地 Mock")

        # 本地 Mock 回退（当 API key 未配置或调用失败时）
        if not api_success:
            total_tokens, assistant_reply = await self._mock_stream_response(message, model)
            api_success = True

        # 发送 token 统计 + conversation_id
        resp_stats = {"tokens": total_tokens, "mock": is_mock}
        if conv_id:
            resp_stats["conversation_id"] = conv_id
        self.write(
            f"event: stats\ndata: {json.dumps(resp_stats)}\n\n"
        )
        await self.flush()

        # 记录 Token 消耗到数据库
        if total_tokens > 0:
            AiModelRepository.add_tokens(model_id, total_tokens)

        # 多轮对话：保存用户消息与 AI 回复
        if conv_id:
            ConversationRepository.add_message(conv_id, "user", message, 0)
            ConversationRepository.add_message(
                conv_id, "assistant",
                assistant_reply,
                total_tokens
            )

        # 审计日志
        from app.utils.security import write_audit_log
        write_audit_log(
            action="CHAT",
            username=self.current_user,
            target=f"model:{model_id}",
            detail=f"tokens={total_tokens}, msg_len={len(message)}",
            client_ip=self.request.remote_ip or "",
        )

    async def _mock_stream_response(self, message: str, model) -> tuple:
        """
        本地 Mock 流式响应（字符级分片模拟 SSE）。
        无需真实 API，用于演示/开发环境。
        返回 (估算token数, 完整回复文本)。
        """
        system_prompt = model["system_prompt"] or ""
        mock_reply = (
            f"您好！我是 {model['name']}（{model['provider']}）。\n\n"
            f"您刚才问：「{message}」\n\n"
            f"当前为本地 Mock 模式。配置有效的 API Key 后，将自动切换为真实 AI 对话。\n\n"
            f"🔧 系统提示词：{system_prompt[:100] if system_prompt else '（未设置）'}"
        )
        chars = list(mock_reply)
        for i, ch in enumerate(chars):
            self.write(f"data: {json.dumps({'content': ch})}\n\n")
            await self.flush()
            await asyncio.sleep(0.02)  # 模拟流式打字效果
            if i > 0 and i % 20 == 0:
                await asyncio.sleep(0.01)

        self.write(f"data: [DONE]\n\n")
        await self.flush()

        # 估算 token（中文约 1-2 字符/token，英文约 4 字符/token）
        chinese_chars = sum(1 for c in mock_reply if '\u4e00' <= c <= '\u9fff')
        other_chars = len(mock_reply) - chinese_chars
        return max(1, chinese_chars + other_chars // 4), mock_reply


class ModelChatPageHandler(AdminBaseHandler):
    """模型对话测试页面（含多轮对话历史）"""

    @tornado.web.authenticated
    def get(self):
        model_id = self.get_query_argument("model_id", None)
        models_data, _ = AiModelRepository.get_all(page=1, page_size=50)
        conversations = ConversationRepository.get_all(username=self.current_user, limit=50)

        selected_model = None
        if model_id:
            try:
                selected_model = AiModelRepository.get_by_id(int(model_id))
            except (ValueError, TypeError):
                pass

        if not selected_model:
            selected_model = AiModelRepository.get_default()
        if not selected_model:
            for m in models_data:
                if m["is_enabled"] == 1:
                    selected_model = m
                    break

        self.render(
            "admin/model_chat.html",
            title="模型测试 — 瞭望与问数系统",
            username=self.current_user,
            models=models_data,
            selected=selected_model,
            conversations=conversations,
            xsrf_token=self.xsrf_token.decode() if isinstance(self.xsrf_token, bytes) else self.xsrf_token,
        )


class ConversationListHandler(AdminBaseHandler):
    """API: 对话列表"""

    @tornado.web.authenticated
    def get(self):
        conversations = ConversationRepository.get_all(username=self.current_user)
        self.write({"code": 0, "items": conversations})


class ConversationCreateHandler(AdminBaseHandler):
    """API: 创建新对话"""

    @tornado.web.authenticated
    def post(self):
        model_id_str = self.get_body_argument("model_id", None)
        model_id = int(model_id_str) if model_id_str else None
        title = self.get_body_argument("title", "新对话").strip()
        conv_id = ConversationRepository.create(
            title=title, model_id=model_id, username=self.current_user
        )
        self.write({"code": 0, "id": conv_id, "title": title})


class ConversationDeleteHandler(AdminBaseHandler):
    """API: 删除对话"""

    @tornado.web.authenticated
    def post(self):
        try:
            conv_id = int(self.get_body_argument("id", 0))
        except (ValueError, TypeError):
            self.write({"code": 1, "msg": "无效的对话ID"})
            return
        conv = ConversationRepository.get_by_id(conv_id)
        if not conv:
            self.write({"code": 1, "msg": "对话不存在"})
            return
        if conv.get("username", "") != self.current_user:
            self.write({"code": 1, "msg": "无权删除此对话"})
            return
        ConversationRepository.delete(conv_id)
        self.write({"code": 0, "msg": "已删除"})


class ConversationMessagesHandler(AdminBaseHandler):
    """API: 获取对话历史消息"""

    @tornado.web.authenticated
    def get(self):
        try:
            conv_id = int(self.get_query_argument("id", 0))
        except (ValueError, TypeError):
            self.write({"code": 1, "msg": "无效的对话ID"})
            return
        # 校验对话归属权，防止 IDOR 越权访问
        conv = ConversationRepository.get_by_id(conv_id)
        if not conv:
            self.write({"code": 1, "msg": "对话不存在"})
            return
        if conv.get("username", "") != self.current_user:
            self.write({"code": 1, "msg": "无权访问此对话"})
            return
        messages = ConversationRepository.get_messages(conv_id, limit=50)
        self.write({"code": 0, "items": messages})
