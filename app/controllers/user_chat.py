"""
user_chat.py — 用户前台智能问数 / AI 对话控制器

提供普通用户使用的 A/B/C/D/E 五区布局对话页面。
支持：SSE 流式对话、@数字员工调用、多轮对话历史、模型切换。
"""
import asyncio
import atexit
import concurrent.futures
import json
import logging
import re
import tornado.web

from app.controllers.base import BaseHandler
from app.models.ai_model import AiModelRepository
from app.models.conversation import ConversationRepository
from app.models.digital_employee import DigitalEmployeeRepository
from app.models.data_warehouse import DataWarehouseRepository
from app.utils.security import write_audit_log

logger = logging.getLogger(__name__)

# 全局线程池
_user_chat_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=8, thread_name_prefix="userchat"
)
atexit.register(_user_chat_executor.shutdown, wait=True)


def _sync_deep_collect(url: str, timeout: int = 30):
    """同步深度采集（在线程池中执行）。"""
    from app.services.deep_collector import deep_fetch
    return deep_fetch(url, timeout=timeout)


# ============================================================
# 页面 Handler
# ============================================================

class UserChatPageHandler(BaseHandler):
    """前台对话主页 — A/B/C/D/E 五区布局"""

    @tornado.web.authenticated
    def get(self):
        # 获取可用模型列表
        models_data, _ = AiModelRepository.get_all(page=1, page_size=50)
        # 选定默认模型
        selected_model = AiModelRepository.get_default()
        if not selected_model:
            for m in models_data:
                if m.get("is_enabled") == 1:
                    selected_model = m
                    break

        # 获取对话历史
        conversations = ConversationRepository.get_all(
            username=self.current_user, limit=50
        )

        # 获取启用的数字员工列表
        employees = DigitalEmployeeRepository.get_enabled()

        self.render(
            "user_chat.html",
            title="智能问数 — 瞭望与问数系统",
            username=self.current_user,
            models=models_data,
            selected=selected_model,
            conversations=conversations,
            employees=employees,
            xsrf_token=(
                self.xsrf_token.decode()
                if isinstance(self.xsrf_token, bytes)
                else self.xsrf_token
            ),
        )


# ============================================================
# API: 模型列表
# ============================================================

class UserModelListHandler(BaseHandler):
    """API: 获取启用的模型列表"""

    @tornado.web.authenticated
    def get(self):
        models_data, _ = AiModelRepository.get_all(page=1, page_size=50)
        items = []
        for m in models_data:
            if m.get("is_enabled") == 1:
                items.append({
                    "id": m["id"],
                    "name": m["name"],
                    "provider": m.get("provider", ""),
                    "model_name": m.get("model_name", ""),
                    "category": m.get("category", ""),
                    "is_default": m.get("is_default", 0),
                })
        self.write({"code": 0, "items": items})


# ============================================================
# API: 数字员工列表（供前端 @ 菜单）
# ============================================================

class UserEmployeeListHandler(BaseHandler):
    """API: 获取启用的数字员工列表"""

    @tornado.web.authenticated
    def get(self):
        employees = DigitalEmployeeRepository.get_enabled()
        items = []
        for e in employees:
            items.append({
                "id": e["id"],
                "name": e["name"],
                "employee_type": e.get("employee_type", "llm"),
                "description": e.get("description", ""),
            })
        self.write({"code": 0, "items": items})


# ============================================================
# API: 对话管理
# ============================================================

class UserConversationListHandler(BaseHandler):
    """API: 用户对话列表"""

    @tornado.web.authenticated
    def get(self):
        conversations = ConversationRepository.get_all(
            username=self.current_user, limit=50
        )
        items = []
        for c in conversations:
            items.append({
                "id": c["id"],
                "title": c.get("title", "新对话"),
                "msg_count": c.get("msg_count", 0),
                "created_at": c.get("created_at", ""),
                "updated_at": c.get("updated_at", ""),
            })
        self.write({"code": 0, "items": items})


class UserConversationCreateHandler(BaseHandler):
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


class UserConversationDeleteHandler(BaseHandler):
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


class UserConversationMessagesHandler(BaseHandler):
    """API: 获取对话消息"""

    @tornado.web.authenticated
    def get(self):
        try:
            conv_id = int(self.get_query_argument("id", 0))
        except (ValueError, TypeError):
            self.write({"code": 1, "msg": "无效的对话ID"})
            return
        conv = ConversationRepository.get_by_id(conv_id)
        if not conv:
            self.write({"code": 1, "msg": "对话不存在"})
            return
        if conv.get("username", "") != self.current_user:
            self.write({"code": 1, "msg": "无权访问此对话"})
            return
        messages = ConversationRepository.get_messages(conv_id, limit=50)
        self.write({"code": 0, "items": messages})


# ============================================================
# 核心: SSE 流式 AI 对话
# ============================================================

class UserChatStreamHandler(BaseHandler):
    """前台 AI 对话 — SSE 流式响应"""

    @tornado.web.authenticated
    async def post(self):
        import time as _time
        _start_time = _time.time()

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
        if not model or model.get("is_enabled") == 0:
            self.write({"code": 1, "msg": "模型不可用"})
            return

        api_base = (model.get("api_base") or "https://api.openai.com/v1").rstrip("/")
        api_key = model.get("api_key") or ""
        model_name = model.get("model_name") or model.get("name")
        system_prompt = model.get("system_prompt") or ""
        temperature = model.get("temperature", 0.7)
        max_tokens = model.get("max_tokens", 4096)

        # 多轮对话历史
        history_messages = []
        conv_id = None
        if conversation_id:
            try:
                conv_id = int(conversation_id)
                conv = ConversationRepository.get_by_id(conv_id)
                if conv and conv.get("username", "") == self.current_user:
                    history_messages = ConversationRepository.get_recent_messages(
                        conv_id, limit=10
                    )
                else:
                    conv_id = None
            except (ValueError, TypeError):
                pass

        # 图表能力注入：教 AI 如何输出 ECharts 图表和表格
        chart_instruction = (
            "\n\n[系统功能说明]\n"
            "你具备数据可视化能力。当用户询问统计数据、趋势分析、对比排名等问题时，"
            "可以在回复末尾附加图表标记，前端将自动渲染为交互式图表。\n\n"
            "图表标记格式：\n"
            "1. ECharts图表: [CHART:{\"title\":{\"text\":\"标题\"},\"xAxis\":{\"type\":\"category\",\"data\":[\"A\",\"B\",\"C\"]},\"yAxis\":{\"type\":\"value\"},\"series\":[{\"data\":[10,20,30],\"type\":\"bar\"}]}]\n"
            "   支持类型: bar(柱状图), line(折线图), pie(饼图), scatter(散点图)\n"
            "2. 数据表格: [TABLE:{\"title\":\"表名\",\"columns\":[\"列1\",\"列2\"],\"rows\":[[\"v1\",\"v2\"],[\"v3\",\"v4\"]]}]\n\n"
            "要求：图表数据必须基于真实查询结果；JSON 必须合法；图表标记放在回复末尾。"
        )

        # 构建消息
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt + chart_instruction})
        else:
            messages.append({"role": "system", "content": chart_instruction})
        messages.extend(history_messages)
        messages.append({"role": "user", "content": message})

        # SSE 响应头
        self.set_header("Content-Type", "text/event-stream")
        self.set_header("Cache-Control", "no-cache")
        self.set_header("Connection", "keep-alive")
        self.set_header("X-Accel-Buffering", "no")

        total_tokens = 0
        api_success = False
        is_mock = True

        # 尝试真实 API
        if api_key:
            from app.utils.security import validate_url_safe
            safe, reason = validate_url_safe(api_base)
            if not safe:
                self.write(
                    f"data: {json.dumps({'error': f'API Base URL 不安全: {reason}'})}\n\n"
                )
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
            }).encode('utf-8')

            def _sync_stream_call():
                import urllib.request
                try:
                    req = urllib.request.Request(
                        f"{api_base}/chat/completions",
                        data=payload,
                        headers={
                            "Content-Type": "application/json; charset=utf-8",
                            "Authorization": f"Bearer {api_key}",
                        },
                    )
                    with urllib.request.urlopen(req, timeout=120) as resp:
                        return resp.read(), None
                except Exception as e:
                    return b"", str(e)

            loop = asyncio.get_event_loop()
            raw_data, err = await loop.run_in_executor(
                _user_chat_executor, _sync_stream_call
            )

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
                            if "usage" in chunk and chunk.get("usage"):
                                total_tokens = chunk["usage"].get("total_tokens", 0)
                        except json.JSONDecodeError:
                            pass
                assistant_reply = "".join(assistant_reply_parts)
                if total_tokens == 0 and content_chars > 0:
                    total_tokens = max(1, content_chars // 2)
                if not assistant_reply:
                    logger.warning("API 返回空响应，回退到本地 Mock")
                    api_success = False
                    is_mock = True
            else:
                logger.warning(f"用户对话 API 调用失败: {err}，回退到本地 Mock")

        # Mock 回退
        if not api_success:
            total_tokens, assistant_reply = await self._mock_chat_response(
                message, model
            )
            api_success = True

        # 发送统计
        elapsed = round(_time.time() - _start_time, 2)
        resp_stats = {"tokens": total_tokens, "mock": is_mock, "elapsed": elapsed}
        if conv_id:
            resp_stats["conversation_id"] = conv_id
        self.write(f"event: stats\ndata: {json.dumps(resp_stats)}\n\n")
        await self.flush()

        # 记录 Token
        if total_tokens > 0:
            AiModelRepository.add_tokens(model_id, total_tokens)

        # 保存对话
        if conv_id:
            ConversationRepository.add_message(conv_id, "user", message, 0)
            ConversationRepository.add_message(
                conv_id, "assistant", assistant_reply, total_tokens
            )

        write_audit_log(
            action="USER_CHAT",
            username=self.current_user,
            target=f"model:{model_id}",
            detail=f"tokens={total_tokens}, msg_len={len(message)}, elapsed={elapsed}s",
            client_ip=self.request.remote_ip or "",
        )

    async def _mock_chat_response(self, message: str, model: dict) -> tuple:
        """本地 Mock 流式响应。返回 (估算token数, 完整回复文本)。"""
        system_prompt = model.get("system_prompt", "")
        mock_reply = (
            f"您好！我是 {model.get('name', 'AI助手')}（{model.get('provider', '未知')}）。\n\n"
            f"您刚才问：「{message}」\n\n"
            f"当前为本地 Mock 模式。配置有效的 API Key 后，将自动切换为真实 AI 对话。\n\n"
            f"🔧 系统提示词：{system_prompt[:100] if system_prompt else '（未设置）'}"
        )

        for ch in mock_reply:
            self.write(f"data: {json.dumps({'content': ch})}\n\n")
            await self.flush()
            await asyncio.sleep(0.015)

        self.write(f"data: [DONE]\n\n")
        await self.flush()

        chinese_chars = sum(1 for c in mock_reply if '\u4e00' <= c <= '\u9fff')
        other_chars = len(mock_reply) - chinese_chars
        return max(1, chinese_chars + other_chars // 4), mock_reply


# ============================================================
# 核心: @数字员工 SSE 流式调用
# ============================================================

class UserEmployeeInvokeHandler(BaseHandler):
    """前台 @数字员工调用 — SSE 流式响应"""

    @tornado.web.authenticated
    async def post(self):
        import time as _time
        _start_time = _time.time()

        try:
            emp_id = int(self.get_body_argument("employee_id", 0))
        except (ValueError, TypeError):
            self.write({"code": 1, "msg": "无效的员工ID"})
            return
        message = self.get_body_argument("message", "").strip()

        if not message:
            self.write({"code": 1, "msg": "消息不能为空"})
            return
        if len(message) > 10000:
            self.write({"code": 1, "msg": "消息过长（最多10000字符）"})
            return

        emp = DigitalEmployeeRepository.get_by_id(emp_id)
        if not emp or emp.get("is_enabled") == 0:
            self.write({"code": 1, "msg": "员工不可用"})
            return

        if emp.get("employee_type") == "api":
            await self._invoke_api_employee(emp, message)
        else:
            await self._invoke_llm_employee(emp, message, _start_time)

    async def _invoke_llm_employee(self, emp: dict, message: str, start_time: float):
        """LLM 型员工调用。"""
        import time as _time

        # 选择模型
        model = None
        if emp.get("model_id"):
            model = AiModelRepository.get_by_id(emp["model_id"])
        if not model or model.get("is_enabled", 0) == 0:
            model = AiModelRepository.get_default()
        if not model:
            models, _ = AiModelRepository.get_all(page=1, page_size=50)
            for m in models:
                if m.get("is_enabled") == 1:
                    model = m
                    break
        if not model:
            self.set_header("Content-Type", "text/event-stream")
            self.set_header("Cache-Control", "no-cache")
            self.write(
                f"data: {json.dumps({'error': '没有可用的AI模型'})}\n\n"
            )
            await self.flush()
            return

        api_base = (model.get("api_base") or "https://api.openai.com/v1").rstrip("/")
        api_key = model.get("api_key") or ""
        model_name = model.get("model_name") or model.get("name")
        system_prompt = emp.get("system_prompt", "") or model.get("system_prompt", "")
        temperature = model.get("temperature", 0.7)
        max_tokens = model.get("max_tokens", 4096)

        # 执行工具调用
        tool_ctx = await self._execute_employee_tools(emp, message)
        warehouse_ctx = ""
        if tool_ctx.get("warehouse_data"):
            items = tool_ctx["warehouse_data"][:5]
            warehouse_ctx = "\n\n[系统注入：数据仓库查询结果]\n"
            for i, item in enumerate(items, 1):
                warehouse_ctx += (
                    f"{i}. 标题: {item.get('title','')}\n"
                    f"   摘要: {item.get('summary','')}\n"
                    f"   来源: {item.get('source_name','')}\n"
                    f"   链接: {item.get('link','')}\n"
                )
            warehouse_ctx += (
                f"共 {tool_ctx['warehouse_count']} 条匹配结果。"
                f"请基于以上真实数据回答用户问题。\n"
            )

        if tool_ctx.get("warehouse_stats"):
            ws = tool_ctx["warehouse_stats"]
            warehouse_ctx += (
                f"\n[系统注入：数据仓库概况] "
                f"总记录 {ws['total']} 条，已深度采集 {ws['deep_collected']} 条。\n"
            )

        if tool_ctx.get("deep_collect_result") and tool_ctx["deep_collect_result"].get("success"):
            dc = tool_ctx["deep_collect_result"]
            warehouse_ctx += (
                f"\n[系统注入：深度采集结果]\n"
                f"标题: {dc.get('title','')}\n"
                f"内容: {dc.get('content','')[:1500]}\n"
            )

        # 构建消息
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt + warehouse_ctx})
        elif warehouse_ctx:
            messages.append({"role": "system", "content": warehouse_ctx})
        messages.append({"role": "user", "content": message})

        # SSE 响应头
        self.set_header("Content-Type", "text/event-stream")
        self.set_header("Cache-Control", "no-cache")
        self.set_header("Connection", "keep-alive")
        self.set_header("X-Accel-Buffering", "no")

        total_tokens = 0
        api_success = False

        if api_key:
            from app.utils.security import validate_url_safe
            safe, reason = validate_url_safe(api_base)
            if not safe:
                self.write(
                    f"data: {json.dumps({'error': f'API Base URL 不安全: {reason}'})}\n\n"
                )
                self.write(f"data: [DONE]\n\n")
                await self.flush()
                return

            payload = json.dumps({
                "model": model_name,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True,
            }).encode('utf-8')

            def _sync_stream_call():
                import urllib.request
                try:
                    req = urllib.request.Request(
                        f"{api_base}/chat/completions",
                        data=payload,
                        headers={
                            "Content-Type": "application/json; charset=utf-8",
                            "Authorization": f"Bearer {api_key}",
                        },
                    )
                    with urllib.request.urlopen(req, timeout=120) as resp:
                        return resp.read(), None
                except Exception as e:
                    return b"", str(e)

            loop = asyncio.get_event_loop()
            raw_data, err = await loop.run_in_executor(
                _user_chat_executor, _sync_stream_call
            )

            if err is None:
                api_success = True
                content_chars = 0
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
                                self.write(
                                    f"data: {json.dumps({'content': content})}\n\n"
                                )
                                await self.flush()
                            if "usage" in chunk and chunk.get("usage"):
                                total_tokens = chunk["usage"].get("total_tokens", 0)
                        except json.JSONDecodeError:
                            pass
                if total_tokens == 0 and content_chars > 0:
                    total_tokens = max(1, content_chars // 2)
            else:
                logger.warning(
                    f"用户员工调用 API 失败: {err}，回退到本地 Mock"
                )

        # Mock 回退
        if not api_success:
            total_tokens = await self._mock_employee_response(emp, message, tool_ctx)

        if total_tokens > 0 and model:
            AiModelRepository.add_tokens(model["id"], total_tokens)

        elapsed = round(_time.time() - start_time, 2)
        self.write(
            f"event: stats\ndata: {json.dumps({'tokens': total_tokens, 'mock': not api_success, 'elapsed': elapsed})}\n\n"
        )
        await self.flush()

        write_audit_log(
            action="USER_EMPLOYEE_INVOKE",
            username=self.current_user,
            target=f"employee:{emp['id']}",
            detail=f"tokens={total_tokens}, msg_len={len(message)}, elapsed={elapsed}s",
            client_ip=self.request.remote_ip or "",
        )

    async def _mock_employee_response(
        self, emp: dict, message: str, tool_results: dict = None
    ) -> int:
        """Mock 数字员工响应。"""
        name = emp.get("name", "数字员工")
        skills_list = []
        try:
            skills_list = json.loads(emp.get("skills", "[]"))
        except (json.JSONDecodeError, TypeError):
            pass
        crawl4ai_on = emp.get("crawl4ai_enabled", 0) == 1

        if tool_results is None:
            tool_results = await self._execute_employee_tools(emp, message)

        lines = [f"🤖 **{name}** 为您服务。\n"]

        intent = tool_results.get("intent", "general")
        if intent == "warehouse_query":
            lines.append(
                f"📊 在数据仓库中搜索「{tool_results.get('keyword', message)}」...\n"
            )
        elif intent == "warehouse_list":
            lines.append("📋 获取数据仓库最新内容...\n")
        elif intent == "deep_collect" and crawl4ai_on:
            lines.append("🕷️ 正在深度采集网页内容...\n")
        elif intent == "warehouse_stats":
            lines.append("📈 数据仓库统计信息...\n")

        if tool_results.get("warehouse_data"):
            lines.append(
                f"\n**数据仓库查询结果**（共 {tool_results['warehouse_count']} 条）：\n"
            )
            for i, item in enumerate(tool_results["warehouse_data"][:5], 1):
                title = item.get("title", "无标题")[:80]
                link = item.get("link", "")[:60]
                source = item.get("source_name", "未知来源")
                summary = (item.get("summary", "") or "")[:100]
                lines.append(f"{i}. **{title}**")
                if summary:
                    lines.append(f"   > {summary}")
                lines.append(f"   📎 来源: {source}")
                if link:
                    lines.append(f"   🔗 {link}")
                lines.append("")
            if tool_results["warehouse_count"] > 5:
                lines.append(
                    f"... 还有 {tool_results['warehouse_count'] - 5} 条结果未显示\n"
                )

        if tool_results.get("deep_collect_result"):
            dc = tool_results["deep_collect_result"]
            if dc.get("success"):
                lines.append(
                    f"\n✅ 深度采集完成！\n"
                    f"- 标题: {dc.get('title', 'N/A')[:100]}\n"
                    f"- 内容长度: {dc.get('content_size', 0)} 字符\n"
                )
                content_preview = (dc.get("content", "") or "")[:500]
                if content_preview:
                    lines.append(f"\n**正文预览**:\n{content_preview}\n...\n")
            else:
                lines.append(
                    f"\n⚠️ 深度采集失败: {dc.get('error', '未知错误')}\n"
                )

        if tool_results.get("warehouse_stats"):
            ws = tool_results["warehouse_stats"]
            lines.append(
                f"\n📈 **数据仓库概况**:\n"
                f"- 总记录数: {ws.get('total', 0)}\n"
                f"- 已深度采集: {ws.get('deep_collected', 0)}\n"
            )

        if (
            not tool_results.get("warehouse_data")
            and not tool_results.get("deep_collect_result")
            and not tool_results.get("warehouse_stats")
        ):
            lines.append(f"\n您问：「{message}」\n")
            skills_text = "、".join(skills_list) if skills_list else "通用助手"
            lines.append(f"🔧 我的技能: {skills_text}")
            if crawl4ai_on:
                lines.append("🕷️ Crawl4ai 网页采集: 已启用")
            lines.append("\n💡 试试这些指令:")
            lines.append("  • 「查看数据仓库」— 列出最新采集数据")
            lines.append("  • 「搜索 AI」— 在数据仓库中搜索关键词")
            if crawl4ai_on:
                lines.append("  • 「深度采集 https://...」— 抓取网页正文")
            lines.append("\n⚠️ 当前为本地智能模式。配置 API Key 后将启用 AI 大模型对话。")

        full_reply = "\n".join(lines)
        for ch in full_reply:
            self.write(f"data: {json.dumps({'content': ch})}\n\n")
            await self.flush()
            await asyncio.sleep(0.01)

        self.write(f"data: [DONE]\n\n")
        await self.flush()

        chinese_chars = sum(1 for c in full_reply if '\u4e00' <= c <= '\u9fff')
        other_chars = len(full_reply) - chinese_chars
        return max(1, chinese_chars + other_chars // 4)

    async def _execute_employee_tools(self, emp: dict, message: str) -> dict:
        """根据用户意图执行工具调用。"""
        result = {"intent": "general"}
        msg_lower = message.lower().strip()
        crawl4ai_on = emp.get("crawl4ai_enabled", 0) == 1

        search_keywords = ["搜索", "查找", "查询", "找", "search", "有没有"]
        list_keywords = [
            "数据仓库", "最新数据", "最近采集", "仓库列表",
            "列出", "有什么数据", "查看数据", "看看数据",
        ]
        stats_keywords = ["统计", "概况", "有多少", "数量"]
        crawl_keywords = ["深度采集", "抓取", "采集网页", "爬取", "crawl", "fetch"]

        # crawl 需同时有关键词+URL，否则继续匹配其他意图
        if any(kw in msg_lower for kw in crawl_keywords) and crawl4ai_on:
            url_match = re.search(r'https?://[^\s]+', message)
            if url_match:
                result["intent"] = "deep_collect"
                result["url"] = url_match.group(0)
        if not result["intent"]:
            if any(kw in msg_lower for kw in stats_keywords):
                result["intent"] = "warehouse_stats"
            elif any(kw in msg_lower for kw in search_keywords):
                result["intent"] = "warehouse_query"
                keyword = message
                for kw in search_keywords:
                    keyword = keyword.replace(kw, "")
                result["keyword"] = keyword.strip() or message
            elif any(kw in msg_lower for kw in list_keywords):
                result["intent"] = "warehouse_list"
            elif len(message) < 20 and not message.startswith("http"):
                result["intent"] = "warehouse_query"
                result["keyword"] = message

        try:
            if result["intent"] in ("warehouse_query", "warehouse_list"):
                keyword = result.get("keyword", "")
                rows, total = DataWarehouseRepository.get_all(
                    page=1, page_size=10, keyword=keyword
                )
                result["warehouse_data"] = [dict(r) for r in rows]
                result["warehouse_count"] = total

            if result["intent"] == "warehouse_stats":
                from app.models.db import get_db
                with get_db() as conn:
                    total = conn.execute(
                        "SELECT COUNT(*) as cnt FROM data_warehouse"
                    ).fetchone()["cnt"]
                    deep = conn.execute(
                        "SELECT COUNT(*) as cnt FROM data_warehouse "
                        "WHERE is_deep_collected = 1"
                    ).fetchone()["cnt"]
                result["warehouse_stats"] = {"total": total, "deep_collected": deep}

            if result["intent"] == "deep_collect" and crawl4ai_on:
                url = result.get("url", "")
                if url:
                    from app.utils.security import validate_url_safe
                    safe, reason = validate_url_safe(url)
                    if safe:
                        try:
                            loop = asyncio.get_event_loop()
                            status, title, content, error = await loop.run_in_executor(
                                _user_chat_executor,
                                lambda: _sync_deep_collect(url),
                            )
                            result["deep_collect_result"] = {
                                "success": status == 200,
                                "title": title,
                                "content": content[:2000] if content else "",
                                "content_size": len(content) if content else 0,
                                "error": error,
                            }
                        except Exception as e:
                            result["deep_collect_result"] = {
                                "success": False,
                                "error": str(e),
                            }
                    else:
                        result["deep_collect_result"] = {
                            "success": False,
                            "error": f"URL 安全校验失败: {reason}",
                        }
        except Exception as e:
            logger.error(f"用户员工工具执行异常: {e}")
            result["tool_error"] = str(e)

        return result

    async def _invoke_api_employee(self, emp: dict, message: str):
        """API 型员工调用。"""
        api_url = emp.get("api_url", "")
        api_method = emp.get("api_method", "GET")
        api_headers_raw = emp.get("api_headers", "{}")
        api_params = emp.get("api_params_template", "")
        api_secret = emp.get("api_secret", "")

        if not api_url:
            self.write({"code": 1, "msg": "API 型员工未配置接口地址"})
            return

        try:
            import urllib.parse
            encoded_msg = urllib.parse.quote(message, safe="")
            api_url = api_url.replace("{message}", encoded_msg)
            # URL 编码防止参数注入（&、= 等特殊字符不能直接拼入查询串）
            api_params = api_params.replace("{message}", encoded_msg)
        except Exception:
            pass

        try:
            headers = json.loads(api_headers_raw) if api_headers_raw else {}
        except (json.JSONDecodeError, TypeError):
            headers = {}

        if api_secret:
            headers["Authorization"] = f"Bearer {api_secret}"

        from app.utils.security import validate_url_safe
        safe, reason = validate_url_safe(api_url)
        if not safe:
            self.write({"code": 1, "msg": f"API URL 不安全: {reason}"})
            return

        import urllib.request

        def _sync_api_call():
            try:
                if api_method == "POST":
                    data = api_params.encode('utf-8') if api_params else None
                    req = urllib.request.Request(
                        api_url, data=data, headers=headers, method="POST"
                    )
                elif api_method == "GET":
                    full_url = api_url
                    if api_params:
                        full_url += ("&" if "?" in api_url else "?") + api_params
                    req = urllib.request.Request(full_url, headers=headers, method="GET")
                else:
                    data = api_params.encode('utf-8') if api_params else None
                    req = urllib.request.Request(
                        api_url, data=data, headers=headers, method=api_method
                    )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    body = resp.read().decode("utf-8", errors="replace")
                    return resp.status, body, None
            except Exception as e:
                return 0, "", str(e)

        loop = asyncio.get_event_loop()
        status, body, err = await loop.run_in_executor(
            _user_chat_executor, _sync_api_call
        )

        if err:
            self.write({"code": 1, "msg": f"API 调用失败: {err}"})
        else:
            try:
                result = json.loads(body)
                self.write({"code": 0, "data": result, "status": status})
            except json.JSONDecodeError:
                self.write({"code": 0, "data": {"raw": body}, "status": status})

        write_audit_log(
            action="USER_EMPLOYEE_INVOKE",
            username=self.current_user,
            target=f"employee:{emp['id']}",
            detail=f"type=api, status={status}",
            client_ip=self.request.remote_ip or "",
        )
