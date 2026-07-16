"""
admin_employee.py — 数字化员工控制器

管理 LLM 型 / API 型数字化员工（新增/编辑/删除/启停/调用）。
参考 admin_model.py 的 Handler 模式。
"""
import asyncio
import atexit
import concurrent.futures
import json
import logging
import tornado.web
from app.controllers.admin_base import AdminBaseHandler
from app.models.digital_employee import (
    DigitalEmployeeRepository, EMPLOYEE_TYPES,
)
from app.models.ai_model import AiModelRepository
from app.models.api_interface import (
    ApiInterfaceRepository,
    normalize_api_method,
    normalize_headers,
    redact_sensitive_headers,
    restore_redacted_headers,
)
from app.models.skill import SkillRepository
from app.models.mcp_tool import MCPToolRepository
from app.models.data_warehouse import DataWarehouseRepository
from app.utils.security import has_crlf, write_audit_log
from app.utils.safe_http import SafeHttpError, safe_http_request

logger = logging.getLogger(__name__)

# SSE 对话线程池（复用模型引擎的线程池模式）
_invoke_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="emp")
atexit.register(_invoke_executor.shutdown, wait=True)


def _sync_deep_collect(url: str, timeout: int = 30):
    """同步深度采集（在线程池中执行）。"""
    from app.services.deep_collector import deep_fetch
    return deep_fetch(url, timeout=timeout)


class EmployeeListHandler(AdminBaseHandler):
    """数字员工列表页（卡片式）"""

    @tornado.web.authenticated
    def get(self):
        try:
            page = max(1, int(self.get_query_argument("page", 1)))
        except (ValueError, TypeError):
            page = 1
        employee_type = self.get_query_argument("type", "").strip()
        rows, total = DigitalEmployeeRepository.get_all(
            page=page, page_size=12, employee_type=employee_type
        )
        total_pages = max(1, (total + 12 - 1) // 12)
        stats = DigitalEmployeeRepository.get_stats()

        # 预解析 skills（v0.7: 存储技能 ID 数组，需从技能库解析名称；
        # 兼容旧格式：字符串标签数组）
        import json as _json
        for emp in rows:
            try:
                raw_skills = _json.loads(emp.get("skills", "[]"))
            except (_json.JSONDecodeError, TypeError):
                raw_skills = []
            resolved = SkillRepository.resolve_by_ids(raw_skills) if raw_skills and isinstance(raw_skills[0], int) else []
            emp["skills_list"] = [s["name"] for s in resolved] if resolved else []
            # 兼容旧格式（字符串标签）
            if not emp["skills_list"] and raw_skills and isinstance(raw_skills[0], str):
                resolved_names = SkillRepository.resolve_by_names(raw_skills)
                emp["skills_list"] = [s["name"] for s in resolved_names] if resolved_names else raw_skills
                # 标记为旧格式（模板中可区分显示）
                emp["skills_legacy"] = True
            # v0.10: 解析 MCP 工具名称
            try:
                raw_tool_ids = _json.loads(emp.get("mcp_tool_ids", "[]"))
            except (_json.JSONDecodeError, TypeError):
                raw_tool_ids = []
            if raw_tool_ids:
                mcp_tool_rows = MCPToolRepository.get_by_ids(raw_tool_ids)
                emp["mcp_tools_list"] = [t["display_name"] for t in mcp_tool_rows]
            else:
                emp["mcp_tools_list"] = []
            # v1.6.0: API 型员工解析绑定的 MCP 工具名称（原地更新 rows[i]）
            if emp.get("employee_type") == "api":
                resolved = DigitalEmployeeRepository.resolve_mcp_tool_info(emp)
                for key in ("mcp_tool_name", "mcp_tool_category", "mcp_tool_type"):
                    emp[key] = resolved.get(key, "")
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
            try:
                emp = DigitalEmployeeRepository.get_by_id(int(emp_id))
            except (ValueError, TypeError):
                self.write('<script>alert("无效的员工ID");window.history.back();</script>')
                return
            if not emp:
                self.write('<script>alert("员工不存在");window.history.back();</script>')
                return

        # 获取启用的模型列表（供 LLM 型选择模型）
        models, _ = AiModelRepository.get_all(
            page=1, page_size=50, model_scope="admin", owner_username=""
        )
        enabled_models = [m for m in models if m.get("is_enabled") == 1]
        current_interface_id = emp.get("api_interface_id") if emp else None
        if emp and emp.get("api_headers"):
            # 不在员工编辑页回显 Authorization / Cookie / X-API-Key 等敏感 Header；
            # 若用户不改动脱敏值，POST 时恢复为原始 headers，避免误保存 ******。
            emp = dict(emp)
            emp["api_headers"] = redact_sensitive_headers(emp.get("api_headers", "{}"))
        api_interfaces = ApiInterfaceRepository.get_for_employee_form(current_interface_id)

        # 获取启用的技能库（供技能选择器使用）
        skills_library = SkillRepository.get_enabled()

        # 获取启用的 MCP 工具（供工具选择器使用，v0.10 / v1.6.0 API 型员工 MCP 选择）
        mcp_tools = MCPToolRepository.get_enabled()
        mcp_categories = MCPToolRepository.get_categories()

        self.render(
            "admin/employee_form.html",
            title="编辑员工" if emp else "新增员工",
            username=self.current_user,
            employee=emp,
            employee_types=EMPLOYEE_TYPES,
            models=enabled_models,
            api_interfaces=api_interfaces,
            skills_library=skills_library,
            mcp_tools=mcp_tools,
            mcp_categories=mcp_categories,
            mcp_tools_all=mcp_tools,
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
        # v0.8: crawl4ai_enabled 已废弃，crawl4ai 能力通过 mcp_tool_ids 控制
        crawl4ai_enabled = 0

        # 解析技能选择（v0.7: 从技能库多选，存储技能 ID 数组）
        skill_ids = self.get_body_arguments("skill_ids")
        try:
            skills = [int(sid) for sid in skill_ids if sid.strip()]
        except (ValueError, TypeError):
            skills = []
        skills_json = json.dumps(skills, ensure_ascii=False)

        # 解析 MCP 工具选择（v0.10: 从工具库多选，存储工具 ID 数组）
        tool_ids = self.get_body_arguments("mcp_tool_ids")
        try:
            mcp_ids = [int(tid) for tid in tool_ids if tid.strip()]
        except (ValueError, TypeError):
            mcp_ids = []
        mcp_tool_ids_json = json.dumps(mcp_ids, ensure_ascii=False)

        # v1.6.0: API 型员工绑定的单个 MCP 工具
        mcp_tool_id_str = self.get_body_argument("mcp_tool_id", "").strip()
        try:
            mcp_tool_id = int(mcp_tool_id_str) if mcp_tool_id_str else None
        except (ValueError, TypeError):
            mcp_tool_id = None

        # API 型字段
        api_url = self.get_body_argument("api_url", "").strip()
        api_method_raw = self.get_body_argument("api_method", "").strip()
        api_method = normalize_api_method(api_method_raw or "GET")
        api_headers_raw = self.get_body_argument("api_headers", "").strip()
        api_params_template = self.get_body_argument("api_params_template", "").strip()
        response_render_template = self.get_body_argument("response_render_template", "").strip()
        api_secret = self.get_body_argument("api_secret", "").strip()
        api_interface_id_str = self.get_body_argument("api_interface_id", "").strip()
        try:
            api_interface_id = int(api_interface_id_str) if api_interface_id_str else None
        except (ValueError, TypeError):
            self.write('<script>alert("接口模板ID格式不正确");window.history.back();</script>')
            return

        existing_emp = None
        if emp_id:
            try:
                existing_emp = DigitalEmployeeRepository.get_by_id(int(emp_id))
            except (ValueError, TypeError):
                existing_emp = None

        current_bound_interface = False
        if employee_type == "api" and api_interface_id:
            interface = ApiInterfaceRepository.get_by_id(api_interface_id)
            current_bound_interface = bool(existing_emp and existing_emp.get("api_interface_id") == api_interface_id)
            if not interface or (interface.get("is_enabled") != 1 and not current_bound_interface):
                self.write('<script>alert("所选接口模板不存在或已禁用");window.history.back();</script>')
                return
            # 创建时支持无 JS/未填字段的服务端兜底；编辑时尊重显式清空/覆盖。
            is_create = not bool(emp_id)
            if is_create and not api_url:
                api_url = interface.get("api_url", "")
            if is_create and not api_method_raw:
                api_method = interface.get("api_method", "GET")
            if (
                is_create and (not api_headers_raw or api_headers_raw == "{}")
            ) and interface.get("api_headers"):
                api_headers_raw = interface.get("api_headers", "{}")
            elif interface.get("api_headers") and not current_bound_interface:
                restored_headers = restore_redacted_headers(api_headers_raw or "{}", interface.get("api_headers", "{}"))
                if restored_headers is not None:
                    api_headers_raw = restored_headers
            if is_create and not api_params_template:
                api_params_template = interface.get("api_params_template", "")
            if is_create and not response_render_template:
                response_render_template = interface.get("response_render_template", "")
            # 仅创建时复制接口密钥；编辑留空仍按 Repository 语义保留员工原密钥。
            if is_create and not api_secret:
                api_secret = interface.get("api_secret", "")
        elif employee_type != "api":
            api_interface_id = None

        if (
            employee_type == "api"
            and existing_emp
            and (not api_interface_id or current_bound_interface)
        ):
            restored_headers = restore_redacted_headers(api_headers_raw or "{}", existing_emp.get("api_headers", "{}"))
            if restored_headers is not None:
                api_headers_raw = restored_headers

        api_method = normalize_api_method(api_method)
        api_headers = normalize_headers(api_headers_raw or "{}")
        if api_headers is None:
            self.write('<script>alert("API Headers 必须是 JSON 对象，且不能包含换行字符");window.history.back();</script>')
            return
        if api_secret and has_crlf(api_secret):
            self.write('<script>alert("API 密钥包含非法换行字符");window.history.back();</script>')
            return

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
                mcp_tool_ids_json, mcp_tool_id,
                api_url, api_method, api_headers, api_params_template,
                response_render_template, api_secret, api_interface_id,
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
                mcp_tool_ids_json, mcp_tool_id,
                api_url, api_method, api_headers, api_params_template,
                response_render_template, api_secret, api_interface_id,
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
        try:
            emp_id = int(self.get_body_argument("employee_id", 0))
        except (ValueError, TypeError):
            self.write({"code": 1, "msg": "无效的员工ID"})
            return
        message = self.get_body_argument("message", "").strip()

        # 先加载员工，根据类型判断是否允许空消息
        emp = DigitalEmployeeRepository.get_by_id(emp_id)
        if not emp or emp["is_enabled"] == 0:
            self.write({"code": 1, "msg": "员工不可用"})
            return

        if not message:
            # API 型员工：检查绑定的 MCP 工具是否需要用户输入
            if emp.get("employee_type") == "api" and emp.get("mcp_tool_id"):
                tool_row = MCPToolRepository.get_by_id(emp["mcp_tool_id"])
                if tool_row:
                    try:
                        input_schema = json.loads(tool_row.get("input_schema", "{}"))
                        required = input_schema.get("required", [])
                    except (json.JSONDecodeError, TypeError):
                        required = []
                    if not required:
                        pass  # 工具无需必填参数（如 get_random_music），允许空消息
                    else:
                        props = input_schema.get("properties", {})
                        friendly = []
                        for field in required:
                            info = props.get(field, {})
                            friendly.append(info.get("description", field))
                        self.write({"code": 1, "msg": f"请输入{'/'.join(friendly)}"})
                        return
                else:
                    self.write({"code": 1, "msg": "消息不能为空"})
                    return
            else:
                self.write({"code": 1, "msg": "消息不能为空"})
                return

        # 消息长度限制（防止滥用）
        if len(message) > 10000:
            self.write({"code": 1, "msg": "消息过长（最多10000字符）"})
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
            model = AiModelRepository.get_by_id(emp["model_id"], include_api_key=True)
            if model and model.get("model_scope", "admin") != "admin":
                model = None
        if not model or model.get("is_enabled", 0) == 0:
            model = AiModelRepository.get_default(include_api_key=True)
        if not model:
            models, _ = AiModelRepository.get_all(
                page=1, page_size=50, include_api_key=True,
                model_scope="admin", owner_username=""
            )
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

        # 注入数据仓库上下文：让 LLM 型员工能引用真实数据
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
            warehouse_ctx += f"共 {tool_ctx['warehouse_count']} 条匹配结果。请基于以上真实数据回答用户问题。\n"

        if tool_ctx.get("warehouse_stats"):
            ws = tool_ctx["warehouse_stats"]
            warehouse_ctx += f"\n[系统注入：数据仓库概况] 总记录 {ws['total']} 条，已深度采集 {ws['deep_collected']} 条。\n"

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
            safe, reason, _ = validate_url_safe(api_base)
            if not safe:
                self.write(f"data: {json.dumps({'error': f'API Base URL 不安全: {reason}'})}\n\n")
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
                """在线程池中执行受限、安全的模型 HTTP 调用。"""
                try:
                    response = safe_http_request(
                        f"{api_base}/chat/completions",
                        method="POST",
                        body=payload,
                        headers={
                            "Content-Type": "application/json; charset=utf-8",
                            "Authorization": f"Bearer {api_key}",
                        },
                        timeout=120,
                        max_bytes=8 * 1024 * 1024,
                    )
                    if 300 <= response.status < 400:
                        return b"", "模型接口不允许重定向"
                    return response.body, None
                except Exception as e:
                    return b"", str(e)

            loop = asyncio.get_event_loop()
            raw_data, err = await loop.run_in_executor(_invoke_executor, _sync_stream_call)

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
                            chunk_data = json.loads(data_str)
                            delta = chunk_data.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                content_chars += len(content)
                                self.write(f"data: {json.dumps({'content': content})}\n\n")
                                await self.flush()
                            if "usage" in chunk_data and chunk_data["usage"]:
                                total_tokens = chunk_data["usage"].get("total_tokens", 0)
                        except json.JSONDecodeError:
                            pass
                if total_tokens == 0 and content_chars > 0:
                    total_tokens = max(1, content_chars // 2)
            else:
                logger.warning(f"数字员工 API 调用失败: {err}，回退到本地 Mock")

        # Mock 回退（复用已执行的 tool_ctx，避免双重执行昂贵操作）
        if not api_success:
            total_tokens = await self._mock_llm_response(emp, message, tool_ctx)

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

    async def _mock_llm_response(self, emp: dict, message: str, tool_results: dict = None) -> int:
        """LLM 型员工智能响应：解析意图 → 执行工具 → 格式化回复。
        
        Args:
            tool_results: 可选，调用方已执行的工具结果（避免双重执行）
        """
        name = emp.get("name", "数字员工")
        skills_list = []
        try:
            skills_list = json.loads(emp.get("skills", "[]"))
        except (json.JSONDecodeError, TypeError):
            pass
        # v0.8: crawl4ai_enabled 已废弃，深度采集能力通过 MCP 工具权限控制

        # 1. 执行工具调用：根据意图自动查询数据仓库 / 触发采集
        if tool_results is None:
            tool_results = await self._execute_employee_tools(emp, message)

        # 2. 构建智能回复
        lines = [f"🤖 **{name}** 为您服务。\n"]

        # 意图识别摘要
        intent = tool_results.get("intent", "general")
        if intent == "warehouse_query":
            lines.append(f"📊 在数据仓库中搜索「{tool_results.get('keyword', message)}」...\n")
        elif intent == "warehouse_list":
            lines.append("📋 获取数据仓库最新内容...\n")
        elif intent == "deep_collect":
            lines.append("🕷️ 正在深度采集网页内容...\n")
        elif intent == "warehouse_stats":
            lines.append("📈 数据仓库统计信息...\n")

        # 工具执行结果
        if tool_results.get("warehouse_data"):
            lines.append(f"\n**数据仓库查询结果**（共 {tool_results['warehouse_count']} 条）：\n")
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
                lines.append(f"... 还有 {tool_results['warehouse_count'] - 5} 条结果未显示\n")

        if tool_results.get("deep_collect_result"):
            dc = tool_results["deep_collect_result"]
            if dc.get("success"):
                lines.append(f"\n✅ 深度采集完成！\n- 标题: {dc.get('title', 'N/A')[:100]}\n- 内容长度: {dc.get('content_size', 0)} 字符\n")
                content_preview = (dc.get("content", "") or "")[:500]
                if content_preview:
                    lines.append(f"\n**正文预览**:\n{content_preview}\n...\n")
            else:
                lines.append(f"\n⚠️ 深度采集失败: {dc.get('error', '未知错误')}\n")

        if tool_results.get("warehouse_stats"):
            ws = tool_results["warehouse_stats"]
            lines.append(f"\n📈 **数据仓库概况**:\n- 总记录数: {ws.get('total', 0)}\n- 已深度采集: {ws.get('deep_collected', 0)}\n")

        if not tool_results.get("warehouse_data") and not tool_results.get("deep_collect_result") and not tool_results.get("warehouse_stats"):
            lines.append(f"\n您问：「{message}」\n")
            # v0.7: skills 存储的是 ID 数组，需解析为技能名称用于展示
            if skills_list and isinstance(skills_list[0], int):
                try:
                    resolved = SkillRepository.resolve_by_ids(skills_list)
                    skill_names = [s["name"] for s in resolved]
                except Exception:
                    skill_names = [str(s) for s in skills_list]
            else:
                skill_names = [str(s) for s in skills_list] if skills_list else []
            skills_text = "、".join(skill_names) if skill_names else "通用助手"
            lines.append(f"🔧 我的技能: {skills_text}")
            lines.append(f"\n💡 试试这些指令:")
            lines.append(f"  • 「查看数据仓库」— 列出最新采集数据")
            lines.append(f"  • 「搜索 AI」— 在数据仓库中搜索关键词")
            lines.append(f"\n⚠️ 当前为本地智能模式。配置 API Key 后将启用 AI 大模型对话。")

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
        """根据用户消息意图执行对应的工具调用。返回工具执行结果字典。"""
        result = {"intent": "general"}
        msg_lower = message.lower().strip()
        # v0.8: crawl4ai_enabled 已废弃，深度采集能力通过 MCP 工具权限控制

        # 意图: 搜索数据仓库
        search_keywords = ["搜索", "查找", "查询", "找", "search", "数据仓库里有", "有没有"]
        list_keywords = ["数据仓库", "最新数据", "最近采集", "仓库列表", "列出", "有什么数据", "查看数据", "看看数据"]
        stats_keywords = ["统计", "概况", "有多少", "数量"]
        crawl_keywords = ["深度采集", "抓取", "采集网页", "爬取", "crawl", "fetch"]

        # 检测意图（crawl 需同时有关键词+URL，否则继续匹配其他意图）
        if any(kw in msg_lower for kw in crawl_keywords):
            # 提取 URL
            import re
            url_match = re.search(r'https?://[^\s]+', message)
            if url_match:
                result["intent"] = "deep_collect"
                result["url"] = url_match.group(0)
        if not result["intent"]:
            if any(kw in msg_lower for kw in stats_keywords):
                result["intent"] = "warehouse_stats"
            elif any(kw in msg_lower for kw in search_keywords):
                result["intent"] = "warehouse_query"
                # 提取搜索关键词（去掉指令词）
                keyword = message
                for kw in search_keywords:
                    keyword = keyword.replace(kw, "")
                result["keyword"] = keyword.strip() or message
            elif any(kw in msg_lower for kw in list_keywords):
                result["intent"] = "warehouse_list"
            elif len(message) < 20 and not message.startswith("http"):
                # 短消息可能是关键词搜索
                result["intent"] = "warehouse_query"
                result["keyword"] = message

        # 执行工具
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
                    total = conn.execute("SELECT COUNT(*) as cnt FROM data_warehouse").fetchone()["cnt"]
                    deep = conn.execute(
                        "SELECT COUNT(*) as cnt FROM data_warehouse WHERE is_deep_collected = 1"
                    ).fetchone()["cnt"]
                result["warehouse_stats"] = {"total": total, "deep_collected": deep}

            if result["intent"] == "deep_collect":
                url = result.get("url", "")
                if url:
                    from app.utils.security import validate_url_safe
                    safe, reason, _ = validate_url_safe(url)
                    if safe:
                        try:
                            loop = asyncio.get_event_loop()
                            status, title, content, error = await loop.run_in_executor(
                                _invoke_executor,
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
                            result["deep_collect_result"] = {"success": False, "error": str(e)}
                    else:
                        result["deep_collect_result"] = {"success": False, "error": f"URL 安全校验失败: {reason}"}
        except Exception as e:
            logger.error(f"员工工具执行异常: {e}")
            result["tool_error"] = str(e)

        return result

    async def _invoke_api_employee(self, emp: dict, message: str):
        """API 型员工调用 — v1.6.0: 优先 MCP 工具委托，回退 HTTP 直连。"""
        mcp_tool_id = emp.get("mcp_tool_id")

        if mcp_tool_id:
            # ── 新架构：通过 MCP 工具统一调度 ──
            await self._invoke_api_via_mcp(emp, message, mcp_tool_id)
        else:
            # ── 旧架构兼容：直接 HTTP 调用 ──
            await self._invoke_api_employee_legacy(emp, message)

    async def _invoke_api_via_mcp(self, emp: dict, message: str, mcp_tool_id: int):
        """通过 MCP 工具调用 API 员工（v1.6.0 新架构）。"""
        tool_row = MCPToolRepository.get_by_id(mcp_tool_id)
        if not tool_row or tool_row.get("is_enabled") != 1:
            self.write({"code": 1, "msg": "绑定的 MCP 工具不存在或已禁用"})
            return

        # 尝试从已注册的 MCPServer 获取工具，失败则实时构建
        from app.mcp.server import MCPServer
        from app.mcp.registry import _build_tool_from_db_row  # noqa: F401

        server = MCPServer.get_instance()
        tool = server.get_tool(tool_row["name"])
        if not tool:
            tool = _build_tool_from_db_row(tool_row)

        if not tool:
            self.write({"code": 1, "msg": "MCP 工具加载失败，请检查工具配置"})
            return

        # 构建调用参数：优先使用 input_schema 中的 properties 作为参数
        arguments = {"message": message}
        try:
            input_schema = json.loads(tool_row.get("input_schema", "{}"))
            props = input_schema.get("properties", {})
            if not props:
                arguments = {}
            elif "message" in props:
                arguments = {"message": message}
            elif "query" in props:
                arguments = {"query": message}
            elif "keyword" in props:
                arguments = {"keyword": message}
            elif "prompt" in props:
                arguments = {"prompt": message}
            else:
                required = input_schema.get("required", [])
                if required and required[0] in props:
                    arguments = {required[0]: message}
                elif props:
                    arguments = {next(iter(props)): message}
            # 如果 schema 定义了额外必填字段，尝试给默认值
            for key, prop in props.items():
                if key not in arguments and "default" in prop:
                    arguments[key] = prop["default"]
        except (json.JSONDecodeError, TypeError):
            pass

        try:
            result = await tool.call(arguments)
        except Exception as e:
            logger.error(f"MCP 工具执行失败: {tool_row['name']} — {e}", exc_info=True)
            self.write({"code": 1, "msg": f"MCP 工具执行失败: {str(e)}"})
            return

        # 应用响应渲染模板
        response_template = emp.get("response_render_template", "")
        if response_template:
            try:
                # 简单的模板变量替换
                rendered = response_template.replace("{message}", message)
                for key, val in (result if isinstance(result, dict) else {}).items():
                    if isinstance(val, (str, int, float, bool)):
                        rendered = rendered.replace("{" + key + "}", str(val))
                # 尝试 JSON 输出
                try:
                    self.write({"code": 0, "data": json.loads(rendered)})
                except (json.JSONDecodeError, TypeError):
                    self.write({"code": 0, "data": {"rendered": rendered, "raw": result}})
            except Exception:
                self.write({"code": 0, "data": result})
        else:
            self.write({"code": 0, "data": result})

        write_audit_log(
            action="EMPLOYEE_INVOKE",
            username=self.current_user,
            target=f"employee:{emp['id']}",
            detail=f"type=api(mcp), tool={tool_row['name']}",
            client_ip=self.request.remote_ip or "",
        )

    async def _invoke_api_employee_legacy(self, emp: dict, message: str):
        """API 型员工调用（旧架构兼容）：HTTP 代理 → JSON 响应。"""
        import urllib.parse

        api_url = emp.get("api_url", "")
        api_method = normalize_api_method(emp.get("api_method", "GET"))
        api_headers_raw = emp.get("api_headers", "{}")
        api_params = emp.get("api_params_template", "")
        api_secret = emp.get("api_secret", "")

        if not api_url:
            self.write({"code": 1, "msg": "API 型员工未配置接口地址"})
            return

        # 替换模板变量（URL 编码防止参数注入）
        try:
            encoded_msg = urllib.parse.quote(message, safe="", encoding="utf-8")
            api_url = api_url.replace("{message}", encoded_msg).replace("{message_raw}", encoded_msg)
            api_params = api_params.replace("{message}", encoded_msg).replace("{message_raw}", message)
        except Exception as e:
            logger.warning(f"URL 模板替换失败: {e}，使用原始 URL")

        # 确保 URL 不含未编码的非 ASCII 字符
        try:
            api_url = urllib.parse.quote(api_url, safe=":/?#[]@!$&'()*+,;=%-", encoding="utf-8")
        except Exception:
            pass

        normalized_headers = normalize_headers(api_headers_raw or "{}")
        if normalized_headers is None:
            self.write({"code": 1, "msg": "API Headers 配置非法"})
            return
        headers = json.loads(normalized_headers)

        if api_secret:
            if has_crlf(api_secret):
                self.write({"code": 1, "msg": "API 密钥配置非法"})
                return
            if not any(str(k).lower() == "authorization" for k in headers):
                headers["Authorization"] = f"Bearer {api_secret}"

        from app.utils.security import validate_url_safe
        safe, reason, _ = validate_url_safe(api_url)
        if not safe:
            self.write({"code": 1, "msg": f"API URL 不安全: {reason}"})
            return

        def _sync_api_call():
            try:
                request_url = api_url
                data = None
                if api_method == "POST":
                    data = api_params.encode('utf-8') if api_params else None
                elif api_method == "GET":
                    if api_params:
                        request_url += ("&" if "?" in api_url else "?") + api_params
                else:
                    # PUT, DELETE, PATCH 等方法
                    data = api_params.encode('utf-8') if api_params else None
                request_url = urllib.parse.quote(
                    request_url, safe=":/?#[]@!$&'()*+,;=%-", encoding="utf-8"
                )
                resp = safe_http_request(
                    request_url,
                    method=api_method,
                    headers=headers,
                    body=data,
                    timeout=30,
                    max_bytes=256 * 1024,
                )
                body = resp.body.decode("utf-8", errors="replace")
                if resp.status >= 400:
                    return resp.status, body, f"HTTP {resp.status}: {body[:500]}"
                return resp.status, body, None
            except SafeHttpError as e:
                return 0, "", str(e)
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
            detail=f"type=api(legacy), status={status}",
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
            try:
                selected = DigitalEmployeeRepository.get_by_id(int(emp_id))
            except (ValueError, TypeError):
                pass

        self.render(
            "admin/employee_test.html",
            title="员工测试 — 瞭望与问数系统",
            username=self.current_user,
            employees=employees,
            selected=selected,
            xsrf_token=self.xsrf_token.decode() if isinstance(self.xsrf_token, bytes) else self.xsrf_token,
        )
