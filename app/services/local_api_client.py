"""本地接口进程内调用客户端 — 基于函数注册表，零网络开销。"""

import asyncio
import logging
import urllib.parse
from typing import Any, Callable, Dict

logger = logging.getLogger(__name__)

# 函数注册表: local_handler → Callable
_LOCAL_HANDLER_MAP: Dict[str, Callable] = {}


def _render_url_template(url: str, params: Dict[str, Any]) -> str:
    """Substitute encoded parameters in supported API URL template formats."""
    rendered = url
    for key, value in params.items():
        encoded = urllib.parse.quote(str(value), safe="")
        rendered = rendered.replace(f"{{{{{key}}}}}", encoded)
        rendered = rendered.replace(f"{{{key}}}", encoded)
    return rendered


def register_local_handler(handler_key: str, func: Callable):
    """注册本地接口处理函数。"""
    _LOCAL_HANDLER_MAP[handler_key] = func
    logger.info(f"注册本地接口: {handler_key}")


def _init_local_handlers():
    """系统启动时自动注册所有本地接口处理函数。
    复用 builtin_tools/ 中已有的函数，不做任何重构。"""
    from app.mcp.builtin_tools.warehouse_tools import (
        _search_warehouse, _get_recent_warehouse_data, _get_warehouse_stats,
        _search_warehouse_fulltext, _get_warehouse_by_id,
    )
    from app.mcp.builtin_tools.collect_tools import (
        _collect_web_data, _deep_collect_url, _list_watch_sources,
    )
    from app.mcp.builtin_tools.media_tools import (
        _generate_image, _generate_video,
    )
    from app.mcp.builtin_tools.employee_tools import (
        _list_digital_employees, _invoke_digital_employee,
    )
    from app.mcp.builtin_tools.model_tools import (
        _list_ai_models, _get_default_model,
    )
    from app.mcp.builtin_tools.chat_tools import (
        _list_conversations, _get_conversation_messages,
    )
    from app.mcp.builtin_tools.crawl4ai_tools import (
        _collect_with_crawl4ai, _batch_deep_collect,
    )
    from app.mcp.builtin_tools.system_tools import (
        _load_skill, _get_system_stats,
    )

    register_local_handler("warehouse/search", _search_warehouse)
    register_local_handler("warehouse/recent", _get_recent_warehouse_data)
    register_local_handler("warehouse/stats", _get_warehouse_stats)
    register_local_handler("warehouse/fulltext", _search_warehouse_fulltext)
    register_local_handler("warehouse/by_id", _get_warehouse_by_id)
    register_local_handler("collect/web", _collect_web_data)
    register_local_handler("collect/deep", _deep_collect_url)
    register_local_handler("collect/sources", _list_watch_sources)
    register_local_handler("employee/list", _list_digital_employees)
    register_local_handler("employee/invoke", _invoke_digital_employee)
    register_local_handler("model/list", _list_ai_models)
    register_local_handler("model/default", _get_default_model)
    register_local_handler("conversation/list", _list_conversations)
    register_local_handler("conversation/messages", _get_conversation_messages)
    register_local_handler("crawl4ai/collect", _collect_with_crawl4ai)
    register_local_handler("crawl4ai/batch", _batch_deep_collect)
    register_local_handler("media/generate_image", _generate_image)
    register_local_handler("media/generate_video", _generate_video)
    register_local_handler("system/stats", _get_system_stats)
    register_local_handler("skill/load", _load_skill)

    # 触发自注册模块（模块加载时自动调用 register_local_handler）
    import app.services.collector  # noqa: F401  → collector/fetch
    import app.services.deep_collector  # noqa: F401  → collector/deep-fetch


async def call_local_api(handler_key: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """调用本地接口（进程内函数直调）。

    支持同步和异步函数。
    """
    func = _LOCAL_HANDLER_MAP.get(handler_key)
    if not func:
        return {"success": False, "error": f"未注册的本地接口: {handler_key}"}

    try:
        result = func(**params)
        if asyncio.iscoroutine(result):
            result = await result
    except Exception as e:
        logger.error(f"本地接口 {handler_key} 调用失败: {e}", exc_info=True)
        return {"success": False, "error": str(e)}

    # 统一解包: handler 若已返回 {success, data} 格式，提取 data
    # 否则视为原始数据，包装为 {success: True, data: result}
    if isinstance(result, dict) and "success" in result:
        if result["success"]:
            return {"success": True, "data": result.get("data", result)}
        else:
            return result  # 透传错误
    return {"success": True, "data": result}


def _register_external_proxies():
    """系统启动时：将所有 is_enabled=1 的 external 接口包装为虚拟本地处理器。"""
    from app.models.api_interface import ApiInterfaceRepository
    from app.utils.safe_http import safe_http_request, SafeHttpError

    external_ifaces = ApiInterfaceRepository.get_enabled_external()

    for iface in external_ifaces:
        handler_key = f"proxy/{iface['id']}"

        async def _make_proxy_handler(_iface=iface, **params) -> dict:
            import json as _json
            url = _render_url_template(_iface["api_url"], params)

            headers = _json.loads(_iface.get("api_headers", "{}") or "{}")
            secret = _iface.get("api_secret", "")
            if secret:
                headers = {
                    k: (v.replace("{api_secret}", secret) if isinstance(v, str) else v)
                    for k, v in headers.items()
                }

            def _sync_call():
                try:
                    resp = safe_http_request(
                        url=url,
                        method=_iface.get("api_method", "GET"),
                        headers=headers,
                        timeout=30,
                    )
                    content_type = _iface.get("response_content_type", "json")
                    body_text = resp.body.decode("utf-8", errors="replace")

                    if content_type == "html":
                        return {"success": True, "data": {"html": body_text, "status": resp.status}}
                    elif content_type == "text":
                        return {"success": True, "data": {"text": body_text, "status": resp.status}}
                    else:
                        try:
                            return {"success": True, "data": _json.loads(body_text)}
                        except _json.JSONDecodeError:
                            return {"success": True, "data": {"raw": body_text[:5000], "status": resp.status}}

                except SafeHttpError as e:
                    return {"success": False, "error": f"安全HTTP错误: {e}"}
                except Exception as e:
                    return {"success": False, "error": str(e)}

            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _sync_call)

        _LOCAL_HANDLER_MAP[handler_key] = _make_proxy_handler
        logger.info(f"注册外部接口代理: {handler_key} ← {iface.get('name', '?')} ({iface['api_url'][:60]})")


def _auto_sync_external_proxies_to_api_interfaces():
    """启动时将 external 接口的 local_handler 字段回填为 'proxy/{id}'。"""
    from app.models.db import get_db

    with get_db() as conn:
        conn.execute(
            "UPDATE api_interfaces SET local_handler = 'proxy/' || id "
            "WHERE interface_type = 'external' AND (local_handler IS NULL OR local_handler = '')"
        )
        conn.commit()
