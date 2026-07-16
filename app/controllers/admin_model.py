"""
admin_model.py — 模型引擎控制器

管理 AI 模型配置（多 Provider、多分类、参数设置）。
支持：列表/新增/编辑/删除/启停/清零/设为默认。

注：AI 对话功能已统一迁移至前台 /chat 页面（MCP 架构），
    后台 /admin/model/chat 已废弃。
"""
import json
import logging
import time
import asyncio
import atexit
import concurrent.futures
import tornado.web
from app.controllers.admin_base import AdminBaseHandler
from app.models.ai_model import AiModelRepository, CATEGORIES, PROVIDERS
from app.utils.security import write_audit_log
from app.utils.safe_http import SafeHttpError, safe_http_request

logger = logging.getLogger(__name__)

_model_api_test_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=4, thread_name_prefix="model-api-test"
)
atexit.register(_model_api_test_executor.shutdown, wait=True)


def _model_connection_changed(model: dict, provider: str, api_base: str, model_name: str) -> bool:
    """Return whether endpoint-related fields changed for a model."""
    return any([
        (model.get("provider") or "") != provider,
        (model.get("api_base") or "") != api_base,
        (model.get("model_name") or "") != model_name,
    ])


def _resolve_quick_config_api_key(
    model: dict | None,
    provider: str,
    api_base: str,
    model_name: str,
    submitted_api_key: str,
    clear_key: bool = False,
    confirm_reuse_key: bool = False,
) -> tuple[str, str]:
    """Resolve which API Key should be saved/tested for quick config.

    The quick-config page renders the existing key into a password input so
    the user can verify it and optionally toggle plaintext display. Empty input
    still means "reuse existing key" when endpoint fields are unchanged.
    """
    if clear_key:
        return "", ""
    if submitted_api_key:
        if (
            model and model.get("api_key")
            and submitted_api_key == model.get("api_key")
            and _model_connection_changed(model, provider, api_base, model_name)
            and not confirm_reuse_key
        ):
            return "", (
                "检测到提供商、API Base 或 Model Name 已变更。"
                "若要继续使用当前已保存密钥，请先勾选确认复用；"
                "否则请重新输入新的 API Key"
            )
        return submitted_api_key, ""
    if not model:
        return "", ""
    if _model_connection_changed(model, provider, api_base, model_name) and model.get("api_key"):
        return "", "修改提供商、API Base 或 Model Name 时必须重新输入 API Key"
    return model.get("api_key", "") or "", ""


def _redact_model_test_text(text: str, api_key: str = "") -> str:
    """Remove sensitive values from model test messages before UI/audit output."""
    text = str(text or "")
    if api_key:
        text = text.replace(api_key, "[REDACTED]")
        text = text.replace("Bearer " + api_key, "Bearer [REDACTED]")
    return text[:300]


def _extract_model_test_detail(status: int, reason: str, body: str, api_key: str = "") -> str:
    """Build a short, non-secret detail message for model API test results."""
    try:
        data = json.loads(body or "{}")
    except json.JSONDecodeError:
        return _redact_model_test_text(body or reason or "", api_key)

    if isinstance(data, dict):
        if isinstance(data.get("error"), dict):
            return _redact_model_test_text(data["error"].get("message") or data["error"], api_key)
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            return "接口返回 choices，模型可正常响应"
        if data.get("id") or data.get("model"):
            return "接口返回模型响应元数据"
    return _redact_model_test_text(f"HTTP {status}: {reason}", api_key)


def _test_model_connection_sync(
    provider: str,
    api_base: str,
    api_key: str,
    model_name: str,
    timeout: int = 20,
) -> dict:
    """Synchronously test an OpenAI-compatible chat completions endpoint."""
    start = time.time()
    api_base = (api_base or "").strip().rstrip("/")
    model_name = (model_name or "").strip()
    api_key = (api_key or "").strip()

    if not api_base:
        return {"code": 1, "msg": "请填写 API Base URL", "status": 0}
    if not model_name:
        return {"code": 1, "msg": "请填写 Model Name", "status": 0}
    if not api_key:
        return {"code": 1, "msg": "请填写 API Key", "status": 0}

    url = f"{api_base}/chat/completions"
    payload = json.dumps({
        "model": model_name,
        "messages": [
            {"role": "user", "content": "ping"}
        ],
        "max_tokens": 1,
        "temperature": 0,
        "stream": False,
    }).encode("utf-8")
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Bearer {api_key}",
    }

    try:
        resp = safe_http_request(
            url,
            method="POST",
            headers=headers,
            body=payload,
            timeout=timeout,
            max_bytes=64 * 1024,
        )
        body = resp.body.decode("utf-8", errors="replace")
        elapsed_ms = int((time.time() - start) * 1000)
        detail = _extract_model_test_detail(resp.status, resp.reason, body, api_key)
        ok = 200 <= resp.status < 300 and "error" not in (body[:200].lower())
        if ok:
            msg = f"测试成功：HTTP {resp.status}，{detail}"
        elif resp.status in (401, 403):
            msg = f"认证失败：HTTP {resp.status}，请检查 API Key 或模型权限"
        else:
            msg = f"测试失败：HTTP {resp.status} {resp.reason}，{detail}"
        return {
            "code": 0 if ok else 1,
            "msg": msg,
            "status": resp.status,
            "elapsed_ms": elapsed_ms,
            "provider": provider,
            "resolved_ip": resp.resolved_ip,
        }
    except SafeHttpError as e:
        msg = _redact_model_test_text(str(e), api_key)
        return {
            "code": 1,
            "msg": msg,
            "status": 0,
            "elapsed_ms": int((time.time() - start) * 1000),
            "provider": provider,
        }
    except Exception as e:
        msg = _redact_model_test_text(str(e), api_key)
        logger.warning("模型 API 测试失败: %s", msg)
        return {
            "code": 1,
            "msg": f"模型 API 测试失败: {msg}",
            "status": 0,
            "elapsed_ms": int((time.time() - start) * 1000),
            "provider": provider,
        }


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
                model = AiModelRepository.get_by_id(int(model_id), include_api_key=True)
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
                existing = AiModelRepository.get_by_id(model_id, include_api_key=True)
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


class ModelQuickConfigHandler(AdminBaseHandler):
    """模型 API 快速配置页。

    面向默认普通用户的窄权限入口，仅允许维护当前默认/首个模型的
    API Base、API Key、Provider、Model Name 等基础连接信息，不提供
    删除、启停、设默认和完整模型 CRUD 能力。
    """

    def _get_target_model(self):
        model = AiModelRepository.get_default(include_api_key=True)
        if model:
            return model
        rows, _ = AiModelRepository.get_all(page=1, page_size=1, include_api_key=True)
        return rows[0] if rows else None

    @tornado.web.authenticated
    def get(self):
        msg = self.get_query_argument("msg", "")
        self.render(
            "admin/model_quick_config.html",
            title="模型 API 快速配置 — 瞭望与问数系统",
            username=self.current_user,
            model=self._get_target_model(),
            providers=PROVIDERS,
            categories=CATEGORIES,
            msg=msg,
        )

    @tornado.web.authenticated
    def post(self):
        model = self._get_target_model()
        name = self.get_body_argument("name", "").strip()
        provider = self.get_body_argument("provider", "openai").strip()
        api_base = self.get_body_argument("api_base", "").strip()
        api_key = self.get_body_argument("api_key", "").strip()
        model_name = self.get_body_argument("model_name", "").strip()
        category = self.get_body_argument("category", "text").strip()

        if not name:
            self.write('<script>alert("模型名称不能为空");window.history.back();</script>')
            return
        if provider not in {p["value"] for p in PROVIDERS}:
            self.write('<script>alert("无效的提供商");window.history.back();</script>')
            return
        if category not in {c["value"] for c in CATEGORIES}:
            self.write('<script>alert("无效的模型分类");window.history.back();</script>')
            return

        if model:
            clear_key = self.get_body_argument("clear_key", "0") == "1"
            confirm_reuse_key = self.get_body_argument("confirm_reuse_key", "0") == "1"
            api_key_to_save, key_error = _resolve_quick_config_api_key(
                model, provider, api_base, model_name, api_key, clear_key, confirm_reuse_key
            )
            if key_error:
                self.write(
                    f'<script>alert("{key_error}");window.history.back();</script>'
                )
                return

            ok = AiModelRepository.update(
                model["id"],
                name,
                provider,
                api_base,
                api_key_to_save,
                model_name,
                category,
                model.get("system_prompt", ""),
                float(model.get("temperature", 0.7) or 0.7),
                float(model.get("top_p", 1.0) or 1.0),
                int(model.get("top_k", 50) or 50),
                int(model.get("max_tokens", 4096) or 4096),
                int(model.get("context_size", 8192) or 8192),
            )
            target = f"model:{model['id']}"
            msg = "模型 API 配置已更新" if ok else "模型 API 配置更新失败"
        else:
            new_id = AiModelRepository.create(
                name=name,
                provider=provider,
                api_base=api_base,
                api_key=api_key,
                model_name=model_name,
                category=category,
            )
            if new_id > 0:
                AiModelRepository.set_default(new_id)
            target = f"model:{new_id}" if new_id > 0 else "model:create"
            msg = "模型 API 配置已创建" if new_id > 0 else "模型 API 配置创建失败"

        write_audit_log(
            action="MODEL_QUICK_CONFIG",
            username=self.current_user,
            target=target,
            detail=msg,
            client_ip=self.request.remote_ip or "",
        )
        self.redirect(f"/admin/model/config?msg={msg}")


class ModelQuickConfigTestHandler(AdminBaseHandler):
    """AJAX: 测试模型 API 快速配置是否可连通。"""

    @tornado.web.authenticated
    async def post(self):
        model = ModelQuickConfigHandler._get_target_model(self)
        provider = self.get_body_argument("provider", "openai").strip()
        api_base = self.get_body_argument("api_base", "").strip()
        api_key = self.get_body_argument("api_key", "").strip()
        model_name = self.get_body_argument("model_name", "").strip()
        clear_key = self.get_body_argument("clear_key", "0") == "1"
        confirm_reuse_key = self.get_body_argument("confirm_reuse_key", "0") == "1"

        if provider not in {p["value"] for p in PROVIDERS}:
            self.write({"code": 1, "msg": "无效的提供商", "status": 0})
            return

        api_key_to_test, key_error = _resolve_quick_config_api_key(
            model, provider, api_base, model_name, api_key, clear_key, confirm_reuse_key
        )
        if key_error:
            self.write({"code": 1, "msg": f"{key_error}后再测试", "status": 0})
            return

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            _model_api_test_executor,
            lambda: _test_model_connection_sync(provider, api_base, api_key_to_test, model_name),
        )
        write_audit_log(
            action="MODEL_QUICK_CONFIG_TEST",
            username=self.current_user,
            target=f"model:{model['id']}" if model else "model:draft",
            detail=("success" if result.get("code") == 0 else "failed") + f": {_redact_model_test_text(result.get('msg', ''), api_key_to_test)[:200]}",
            client_ip=self.request.remote_ip or "",
        )
        self.write(result)


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
                "has_key": r.get("has_api_key", False),
            })
        self.write({"code": 0, "total": total, "items": items})



