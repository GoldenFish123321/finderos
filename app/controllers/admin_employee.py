"""
admin_employee.py — 数字化员工控制器

管理 LLM 型 / API 型数字化员工（新增/编辑/删除/启停/调用）。
参考 admin_model.py 的 Handler 模式。
"""
import asyncio
import concurrent.futures
import json
import logging
import tornado.web
from app.controllers.admin_base import AdminBaseHandler
from app.models.digital_employee import (
    DigitalEmployeeRepository, EMPLOYEE_TYPES,
)
from app.models.ai_model import AiModelRepository
from app.utils.security import write_audit_log

logger = logging.getLogger(__name__)

# SSE 对话线程池（复用模型引擎的线程池模式）
_invoke_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="emp")


class EmployeeListHandler(AdminBaseHandler):
    """数字员工列表页（卡片式）"""

    @tornado.web.authenticated
    def get(self):
        page = max(1, int(self.get_query_argument("page", 1)))
        employee_type = self.get_query_argument("type", "").strip()
        rows, total = DigitalEmployeeRepository.get_all(
            page=page, page_size=12, employee_type=employee_type
        )
        total_pages = max(1, (total + 12 - 1) // 12)
        stats = DigitalEmployeeRepository.get_stats()

        # 预解析 skills JSON（避免模板中使用 __import__ 反模式）
        import json as _json
        for emp in rows:
            try:
                emp["skills_list"] = _json.loads(emp.get("skills", "[]"))
            except (_json.JSONDecodeError, TypeError):
                emp["skills_list"] = []
            # JS 安全转义员工名称（用于 confirm 对话框）
            emp["name_js"] = _json.dumps(emp.get("name", ""), ensure_ascii=False)

        self.render(
            "admin/employee_list.html",
            title="数字员工 — 瞭望与问数系统",
            username=self.current_user,
            employees=rows,
            page=page,
            total=total,
            total_pages=total_pages,
            employee_type=employee_type,
            employee_types=EMPLOYEE_TYPES,
            stats=stats,
            xsrf_token=self.xsrf_token.decode() if isinstance(self.xsrf_token, bytes) else self.xsrf_token,
        )


class EmployeeFormHandler(AdminBaseHandler):
    """数字员工新增/编辑表单"""

    @tornado.web.authenticated
    def get(self):
        emp_id = self.get_query_argument("id", None)
        emp = None
        if emp_id:
            emp = DigitalEmployeeRepository.get_by_id(int(emp_id))
            if not emp:
                self.write('<script>alert("员工不存在");window.history.back();</script>')
                return

        # 获取启用的模型列表（供 LLM 型选择模型）
        models, _ = AiModelRepository.get_all(page=1, page_size=50)
        enabled_models = [m for m in models if m.get("is_enabled") == 1]

        self.render(
            "admin/employee_form.html",
            title="编辑员工" if emp else "新增员工",
            username=self.current_user,
            employee=emp,
            employee_types=EMPLOYEE_TYPES,
            models=enabled_models,
        )

    @tornado.web.authenticated
    def post(self):
        emp_id = self.get_body_argument("id", None)
        name = self.get_body_argument("name", "").strip()
        employee_type = self.get_body_argument("employee_type", "llm").strip()
        description = self.get_body_argument("description", "").strip()

        # LLM 型字段
        model_id_str = self.get_body_argument("model_id", "").strip()
        model_id = int(model_id_str) if model_id_str else None
        system_prompt = self.get_body_argument("system_prompt", "").strip()
        skills_raw = self.get_body_argument("skills", "[]").strip()
        crawl4ai_enabled = 1 if self.get_body_argument("crawl4ai_enabled", "0") == "1" else 0

        # 解析 skills（支持 JSON 数组 或 逗号分隔 或 换行分隔）
        try:
            skills = json.loads(skills_raw)
            if not isinstance(skills, list):
                skills = [s.strip() for s in skills_raw.replace("\n", ",").split(",") if s.strip()]
        except (json.JSONDecodeError, TypeError):
            skills = [s.strip() for s in skills_raw.replace("\n", ",").split(",") if s.strip()]
        skills_json = json.dumps(skills, ensure_ascii=False)

        # API 型字段
        api_url = self.get_body_argument("api_url", "").strip()
        api_method = self.get_body_argument("api_method", "GET").strip().upper()
        api_headers_raw = self.get_body_argument("api_headers", "{}").strip()
        api_params_template = self.get_body_argument("api_params_template", "").strip()
        response_render_template = self.get_body_argument("response_render_template", "").strip()
        api_secret = self.get_body_argument("api_secret", "").strip()

        # 验证 API Headers JSON 格式
        try:
            api_headers_parsed = json.loads(api_headers_raw) if api_headers_raw else {}
            api_headers = json.dumps(api_headers_parsed, ensure_ascii=False)
        except (json.JSONDecodeError, TypeError):
            api_headers = "{}"

        if not name:
            self.write('<script>alert("员工名称不能为空");window.history.back();</script>')
            return

        # 员工类型白名单校验
        if employee_type not in ("llm", "api"):
            self.write('<script>alert("无效的员工类型");window.history.back();</script>')
            return

        if emp_id:
            emp_id = int(emp_id)
            ok = DigitalEmployeeRepository.update(
                emp_id, name, employee_type, description,
                model_id, system_prompt, skills_json, crawl4ai_enabled,
                api_url, api_method, api_headers, api_params_template,
                response_render_template, api_secret,
            )
            msg = "更新成功" if ok else "更新失败"
            write_audit_log(
                action="EMPLOYEE_UPDATE",
                username=self.current_user,
                target=f"employee:{emp_id}",
                detail=f"name={name}, type={employee_type}",
                client_ip=self.request.remote_ip or "",
            )
        else:
            new_id = DigitalEmployeeRepository.create(
                name, employee_type, description,
                model_id, system_prompt, skills_json, crawl4ai_enabled,
                api_url, api_method, api_headers, api_params_template,
                response_render_template, api_secret,
            )
            msg = "创建成功" if new_id > 0 else "创建失败"
            if new_id > 0:
                write_audit_log(
                    action="EMPLOYEE_CREATE",
                    username=self.current_user,
                    target=f"employee:{new_id}",
                    detail=f"name={name}, type={employee_type}",
                    client_ip=self.request.remote_ip or "",
                )

        self.redirect(f"/admin/employee?msg={msg}")


class EmployeeDeleteHandler(AdminBaseHandler):
    """删除数字员工"""

    @tornado.web.authenticated
    def post(self):
        emp_id = int(self.get_body_argument("id", 0))
        emp = DigitalEmployeeRepository.get_by_id(emp_id)
        name = emp["name"] if emp else "unknown"
        DigitalEmployeeRepository.delete(emp_id)
        write_audit_log(
            action="EMPLOYEE_DELETE",
            username=self.current_user,
            target=f"employee:{emp_id}",
            detail=f"name={name}",
            client_ip=self.request.remote_ip or "",
        )
        self.redirect("/admin/employee?msg=已删除")


class EmployeeToggleHandler(AdminBaseHandler):
    """启用/禁用数字员工"""

    @tornado.web.authenticated
    def post(self):
        emp_id = int(self.get_body_argument("id", 0))
        status = DigitalEmployeeRepository.toggle_enabled(emp_id)
        if status == -1:
            self.write('<script>alert("员工不存在");window.history.back();</script>')
        else:
            write_audit_log(
                action="EMPLOYEE_TOGGLE",
                username=self.current_user,
                target=f"employee:{emp_id}",
                detail=f"status={'enabled' if status == 1 else 'disabled'}",
                client_ip=self.request.remote_ip or "",
            )
            self.redirect(
                f"/admin/employee?msg={'已启用' if status == 1 else '已禁用'}"
            )


class EmployeeInvokeHandler(AdminBaseHandler):
    """调用数字员工 — SSE 流式响应（LLM 型）或 JSON 响应（API 型）"""

    @tornado.web.authenticated
    async def post(self):
        emp_id = int(self.get_body_argument("employee_id", 0))
        message = self.get_body_argument("message", "").strip()

        if not message:
            self.write({"code": 1, "msg": "消息不能为空"})
            return

        # 消息长度限制（防止滥用）
        if len(message) > 10000:
            self.write({"code": 1, "msg": "消息过长（最多10000字符）"})
            return

        emp = DigitalEmployeeRepository.get_by_id(emp_id)
        if not emp or emp["is_enabled"] == 0:
            self.write({"code": 1, "msg": "员工不可用"})
            return

        if emp["employee_type"] == "api":
            await self._invoke_api_employee(emp, message)
        else:
            await self._invoke_llm_employee(emp, message)

    async def _invoke_llm_employee(self, emp: dict, message: str):
        """LLM 型员工调用：复用模型引擎 SSE 流式对话。"""
        # 选择模型：优先员工指定模型 → 默认模型 → 第一个启用模型
        model = None
        if emp.get("model_id"):
            model = AiModelRepository.get_by_id(emp["model_id"])
        if not model or model.get("is_enabled", 0) == 0:
            model = AiModelRepository.get_default()
        if not model:
            models, _ = AiModelRepository.get_all(page=1, page_size=50)
            for m in models:
                if m["is_enabled"] == 1:
                    model = m
                    break
        if not model:
            self.set_header("Content-Type", "text/event-stream")
            self.set_header("Cache-Control", "no-cache")
            self.write(f"data: {json.dumps({'error': '没有可用的AI模型'})}\n\n")
            await self.flush()
            return

        api_base = (model["api_base"] or "https://api.openai.com/v1").rstrip("/")
        api_key = model["api_key"] or ""
        model_name = model["model_name"] or model["name"]
        system_prompt = emp.get("system_prompt", "") or model.get("system_prompt", "")
        temperature = model["temperature"]
        max_tokens = model["max_tokens"]

        # 构建消息
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
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
                self.write(f"data: {json.dumps({'error': f'API Base URL 不安全: {reason}'})}\n\n")
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
                import urllib.request
                lines = []
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
                        for line in resp:
                            lines.append(line)
                    return lines, None
                except Exception as e:
                    return lines, str(e)

            loop = asyncio.get_event_loop()
            lines, err = await loop.run_in_executor(_invoke_executor, _sync_stream_call)

            if err is None:
                api_success = True
                content_chars = 0
                for line in lines:
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
                            if "usage" in chunk and chunk["usage"]:
                                total_tokens = chunk["usage"].get("total_tokens", 0)
                        except json.JSONDecodeError:
                            pass
                if total_tokens == 0 and content_chars > 0:
                    total_tokens = max(1, content_chars // 2)
            else:
                logger.warning(f"数字员工 API 调用失败: {err}，回退到本地 Mock")

        # Mock 回退
        if not api_success:
            total_tokens = await self._mock_llm_response(emp, message)

        if total_tokens > 0 and model:
            AiModelRepository.add_tokens(model["id"], total_tokens)

        self.write(f"event: stats\ndata: {json.dumps({'tokens': total_tokens, 'mock': not api_success})}\n\n")
        await self.flush()

        write_audit_log(
            action="EMPLOYEE_INVOKE",
            username=self.current_user,
            target=f"employee:{emp['id']}",
            detail=f"tokens={total_tokens}, msg_len={len(message)}",
            client_ip=self.request.remote_ip or "",
        )

    async def _mock_llm_response(self, emp: dict, message: str) -> int:
        """LLM 型员工 Mock 回退响应。"""
        name = emp.get("name", "数字员工")
        skills_list = []
        try:
            skills_list = json.loads(emp.get("skills", "[]"))
        except (json.JSONDecodeError, TypeError):
            pass
        skills_text = "、".join(skills_list) if skills_list else "通用"

        mock_reply = (
            f"🤖 您好！我是 **{name}**。\n\n"
            f"您刚才问：「{message}」\n\n"
            f"🔧 我的技能标签：{skills_text}\n"
            f"📝 系统提示词：{emp.get('system_prompt', '（未设置）')[:100]}\n\n"
            f"⚠️ 当前为 Mock 模式。配置有效的 API Key 后，将自动切换为真实 AI 对话。"
        )
        for ch in mock_reply:
            self.write(f"data: {json.dumps({'content': ch})}\n\n")
            await self.flush()
            await asyncio.sleep(0.015)

        self.write(f"data: [DONE]\n\n")
        await self.flush()

        chinese_chars = sum(1 for c in mock_reply if '\u4e00' <= c <= '\u9fff')
        other_chars = len(mock_reply) - chinese_chars
        return max(1, chinese_chars + other_chars // 4)

    async def _invoke_api_employee(self, emp: dict, message: str):
        """API 型员工调用：HTTP 代理 → JSON 响应。"""
        api_url = emp.get("api_url", "")
        api_method = emp.get("api_method", "GET")
        api_headers_raw = emp.get("api_headers", "{}")
        api_params = emp.get("api_params_template", "")
        api_secret = emp.get("api_secret", "")

        if not api_url:
            self.write({"code": 1, "msg": "API 型员工未配置接口地址"})
            return

        # 替换模板变量
        try:
            api_url = api_url.replace("{message}", message)
            api_params = api_params.replace("{message}", message)
        except Exception:
            pass

        # 解析 headers
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
        import urllib.error

        def _sync_api_call():
            try:
                if api_method == "POST":
                    data = api_params.encode() if api_params else None
                    req = urllib.request.Request(api_url, data=data, headers=headers)
                else:
                    full_url = api_url
                    if api_params:
                        full_url += ("&" if "?" in api_url else "?") + api_params
                    req = urllib.request.Request(full_url, headers=headers)
                with urllib.request.urlopen(req, timeout=30) as resp:
                    body = resp.read().decode("utf-8", errors="replace")
                    return resp.status, body, None
            except Exception as e:
                return 0, "", str(e)

        loop = asyncio.get_event_loop()
        status, body, err = await loop.run_in_executor(_invoke_executor, _sync_api_call)

        if err:
            self.write({"code": 1, "msg": f"API 调用失败: {err}"})
        else:
            try:
                result = json.loads(body)
                self.write({"code": 0, "data": result, "status": status})
            except json.JSONDecodeError:
                self.write({"code": 0, "data": {"raw": body}, "status": status})

        write_audit_log(
            action="EMPLOYEE_INVOKE",
            username=self.current_user,
            target=f"employee:{emp['id']}",
            detail=f"type=api, status={status}",
            client_ip=self.request.remote_ip or "",
        )


class EmployeeApiListHandler(AdminBaseHandler):
    """API: 数字员工列表 JSON（供前端 @ 选择器调用）"""

    @tornado.web.authenticated
    def get(self):
        employees = DigitalEmployeeRepository.get_enabled()
        items = []
        for e in employees:
            items.append({
                "id": e["id"],
                "name": e["name"],
                "employee_type": e["employee_type"],
                "description": e.get("description", ""),
                "has_model": bool(e.get("model_id")),
            })
        self.write({"code": 0, "items": items})


class EmployeeTestPageHandler(AdminBaseHandler):
    """数字员工测试对话页面"""

    @tornado.web.authenticated
    def get(self):
        emp_id = self.get_query_argument("employee_id", None)
        employees = DigitalEmployeeRepository.get_enabled()

        selected = None
        if emp_id:
            selected = DigitalEmployeeRepository.get_by_id(int(emp_id))

        self.render(
            "admin/employee_test.html",
            title="员工测试 — 瞭望与问数系统",
            username=self.current_user,
            employees=employees,
            selected=selected,
            xsrf_token=self.xsrf_token.decode() if isinstance(self.xsrf_token, bytes) else self.xsrf_token,
        )
