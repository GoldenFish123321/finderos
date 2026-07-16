# 本地接口层设计（函数注册表模式）

> 主文档：[README.md](./README.md) — 架构总览

---

## 四、本地接口层设计（函数注册表模式）

### 4.1 设计原则

> ⚠️ **关键决策**: 本地接口**不作为 HTTP Handler 注册**。原因：
> 1. Tornado Handler 依赖完整 HTTP 请求上下文（`self.request`、`self.current_user`），无法在 MCP 工具调用链路（普通用户上下文）中直接实例化
> 2. `AdminBaseHandler.prepare()` 校验管理员权限——普通用户的 MCP 工具调用会被拒绝
> 3. 注册为 HTTP 端点会暴露攻击面（任何人都可 HTTP 访问）

采用**函数注册表直调**模式：

- `builtin_tools/` 中的 Python 函数保持不变（MRP 架构不动）
- 额外维护一个 `_LOCAL_HANDLER_MAP` 字典，映射 `local_handler` 字符串 → 实际函数
- `api_interfaces` 表中的 `local` 型记录仅存储**元数据**（名称、描述、参数模板），`local_handler` 字段指向函数注册表中的键
- 调用时通过 `local_api_client.py` 查表直调，零网络开销
- `api_url` 列对 local 型填 `local://` 占位（迁移时需将 `api_url` 从 `NOT NULL` 改为 `DEFAULT ''`）

### 4.2 本地接口清单

本地接口的 `local_handler` 标识对应 `builtin_tools/` 中已有的函数：

| 分类 | local_handler | 对应 builtin 函数 |
|------|--------------|-------------------|
| 🔍 数据仓库 | `warehouse/search` | `warehouse_tools._search_warehouse` |
| 🔍 数据仓库 | `warehouse/recent` | `warehouse_tools._get_recent_warehouse_data` |
| 🔍 数据仓库 | `warehouse/stats` | `warehouse_tools._get_warehouse_stats` |
| 🔍 数据仓库 | `warehouse/fulltext` | `warehouse_tools._search_warehouse_fulltext` |
| 🔍 数据仓库 | `warehouse/by_id` | `warehouse_tools._get_warehouse_by_id` |
| 🔭 瞭望采集 | `collect/web` | `collect_tools._collect_web_data` |
| 🔭 瞭望采集 | `collect/deep` | `collect_tools._deep_collect_url` |
| 🔭 瞭望采集 | `collect/sources` | `collect_tools._list_watch_sources` |
| 🤖 数字员工 | `employee/list` | `employee_tools._list_digital_employees` |
| 🤖 数字员工 | `employee/invoke` | `employee_tools._invoke_digital_employee` |
| 🧠 AI 模型 | `model/list` | `model_tools._list_ai_models` |
| 🧠 AI 模型 | `model/default` | `model_tools._get_default_model` |
| 💬 对话管理 | `conversation/list` | `chat_tools._list_conversations` |
| 💬 对话管理 | `conversation/messages` | `chat_tools._get_conversation_messages` |
| 🕷️ 爬虫增强 | `crawl4ai/collect` | `crawl4ai_tools._collect_with_crawl4ai` |
| 🕷️ 爬虫增强 | `crawl4ai/batch` | `crawl4ai_tools._batch_deep_collect` |
| 🔧 系统管理 | `system/stats` | `system_tools._get_system_stats` |
| 🔧 系统管理 | `skill/load` | `system_tools._load_skill` |

### 4.3 函数注册表 + 本地接口客户端

```python
# app/services/local_api_client.py (新文件)
"""本地接口进程内调用客户端 — 基于函数注册表，零网络开销。"""

import asyncio
import logging
from typing import Any, Callable, Dict

logger = logging.getLogger(__name__)

# 函数注册表: local_handler → (sync_func, is_async)
_LOCAL_HANDLER_MAP: Dict[str, Callable] = {}


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
    register_local_handler("system/stats", _get_system_stats)
    register_local_handler("skill/load", _load_skill)


async def call_local_api(handler_key: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """调用本地接口（进程内函数直调）。

    支持同步和异步函数。对于同步函数，在线程池中执行以避免阻塞 IOLoop。
    """
    func = _LOCAL_HANDLER_MAP.get(handler_key)
    if not func:
        return {"success": False, "error": f"未注册的本地接口: {handler_key}"}

    import concurrent.futures
    loop = asyncio.get_event_loop()

    try:
        result = func(**params)
        if asyncio.iscoroutine(result):
            result = await result
        # 对于同步但涉及 I/O 的函数（如 _collect_web_data），在线程池中包装
        # 实际由 builtin_tools 内部的 run_in_executor 处理
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"本地接口 {handler_key} 调用失败: {e}", exc_info=True)
        return {"success": False, "error": str(e)}
```

### 4.4 本地接口元数据自动同步

```python
# app/services/local_api_registry.py (新文件)
"""系统启动时同步本地接口元数据到 api_interfaces 表。"""

LOCAL_API_SEEDS = [
    {
        "name": "数据仓库搜索",
        "description": "在数据仓库中搜索关键词相关内容",
        "interface_type": "local",
        "is_system": 1,
        "local_handler": "warehouse/search",
        "api_method": "GET",
        "api_params_template": '{"keyword": "{{keyword}}", "limit": 10}',
    },
    # ... 其余 17 个接口种子数据
]


def sync_local_api_interfaces():
    """同步本地接口到 api_interfaces 表。
    - local 型记录的 api_url 填 'local://'
    - is_system=1，前端隐藏编辑/删除按钮
    - 已存在则更新元数据，不存在则 INSERT
    """
    from app.models.db import get_db

    with get_db() as conn:
        for seed in LOCAL_API_SEEDS:
            existing = conn.execute(
                "SELECT id FROM api_interfaces WHERE name = ?", (seed["name"],)
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE api_interfaces SET description=?, interface_type=?, "
                    "is_system=?, local_handler=?, api_method=?, api_params_template=? "
                    "WHERE id=? AND is_system=1",
                    (seed["description"], seed["interface_type"], seed["is_system"],
                     seed["local_handler"], seed["api_method"],
                     seed["api_params_template"], existing["id"]),
                )
            else:
                conn.execute(
                    "INSERT INTO api_interfaces (name, description, interface_type, "
                    "is_system, local_handler, api_url, api_method, "
                    "api_params_template, is_enabled, sort_order) "
                    "VALUES (?, ?, ?, ?, ?, 'local://', ?, ?, 1, 0)",
                    (seed["name"], seed["description"], seed["interface_type"],
                     seed["is_system"], seed["local_handler"],
                     seed["api_method"], seed["api_params_template"]),
                )
        conn.commit()
```

### 4.5 外部接口代理注册（External → Local Proxy）

> ⚠️ **核心设计决策**: 外部 API 在 `api_interfaces` 中注册后，系统启动时自动将其包装为虚拟本地处理器，
> 注册到 `_LOCAL_HANDLER_MAP`。对上层（MCP 工具、脚本）而言，所有接口都是 `local` 型，完全感知不到外网。

```python
# app/services/local_api_client.py — 在 _init_local_handlers() 之后调用

def _register_external_proxies():
    """系统启动时：将所有 is_enabled=1 的 external 接口包装为虚拟本地处理器。

    每个 external 接口生成 local_handler = 'proxy/{id}'，
    内部通过 safe_http_request 安全地调用外部 API。
    """
    from app.models.api_interface import ApiInterfaceRepository
    from app.utils.safe_http import safe_http_request, SafeHttpError

    external_ifaces = ApiInterfaceRepository.get_enabled_external()

    for iface in external_ifaces:
        handler_key = f"proxy/{iface['id']}"

        async def _make_proxy_handler(iface=iface):
            """闭包捕获 iface，生成异步代理处理器。"""
            import asyncio
            import json as _json
            import urllib.parse

            def _sync_call(params: dict) -> dict:
                """同步 HTTP 调用（在线程池中执行）。"""
                # 1. 构建 URL（替换模板占位符）
                url = iface["api_url"]
                for key, value in params.items():
                    encoded = urllib.parse.quote(str(value), safe="")
                    url = url.replace(f"{{{{{key}}}}}", encoded)
                    url = url.replace(f"{{{key}}}", encoded)

                # 2. 构建请求头（注入密钥）
                headers = _json.loads(iface.get("api_headers", "{}") or "{}")
                secret = iface.get("api_secret", "")
                if secret:
                    headers = {
                        k: (v.replace("{api_secret}", secret) if isinstance(v, str) else v)
                        for k, v in headers.items()
                    }

                try:
                    resp = safe_http_request(
                        url=url,
                        method=iface.get("api_method", "GET"),
                        headers=headers,
                        timeout=30,
                    )
                    content_type = iface.get("response_content_type", "json")
                    body_text = resp.body.decode("utf-8", errors="replace")

                    if content_type == "html":
                        return {"success": True, "data": {"html": body_text, "status": resp.status}}
                    elif content_type == "text":
                        return {"success": True, "data": {"text": body_text, "status": resp.status}}
                    else:
                        # json: 尝试解析
                        try:
                            return {"success": True, "data": _json.loads(body_text)}
                        except _json.JSONDecodeError:
                            return {"success": True, "data": {"raw": body_text[:5000], "status": resp.status}}

                except SafeHttpError as e:
                    return {"success": False, "error": f"安全HTTP错误: {e}"}
                except Exception as e:
                    return {"success": False, "error": str(e)}

            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _sync_call, params)

        # 注册为虚拟本地处理器
        _LOCAL_HANDLER_MAP[handler_key] = _make_proxy_handler
        logger.info(f"注册外部接口代理: {handler_key} ← {iface['name']} ({iface['api_url'][:60]})")


def _auto_sync_external_proxies_to_api_interfaces():
    """启动时将 external 接口的 local_handler 字段回填为 'proxy/{id}'。

    确保 api_interfaces 表中的 external 记录有正确的 local_handler，
    方便 MCP 工具的 data_sources 引用。
    """
    from app.models.db import get_db

    with get_db() as conn:
        conn.execute(
            "UPDATE api_interfaces SET local_handler = 'proxy/' || id "
            "WHERE interface_type = 'external' AND (local_handler IS NULL OR local_handler = '')"
        )
        conn.commit()
```

**启动顺序**（`main.py` 中）：
```python
# 1. 先注册 18 个系统内置本地接口
_init_local_handlers()

# 2. 同步本地接口元数据到 api_interfaces 表
sync_local_api_interfaces()

# 3. 将 external 接口包装为虚拟本地处理器
_auto_sync_external_proxies_to_api_interfaces()
_register_external_proxies()

# 4. 最后加载 MCP 工具（此时所有接口都已是 local）
registry.load_all_from_db()
```

> **效果**：启动后 `_LOCAL_HANDLER_MAP` 包含 18 个系统内置 + N 个 `proxy/{id}` 外部代理。
> MCP 工具和脚本引用的 `interface_id` 全部指向 `local` 型接口，物理外网访问仅发生在 `safe_http_request` 内部。

### 4.6 瞭望采集的特殊处理

瞭望（`collector.py`）不仅做 HTTP 调用，还做 HTML 解析。适配方式：

- 每个瞭望采集源（watch source）在 `api_interfaces` 中对应一条 `external` 型记录
- `response_content_type = 'html'`，`safe_http_request` 返回原始 HTML
- HTML 解析逻辑（`parse_baidu_news`、`parse_sogou_news`）保留在 `collect_tools.py` 中
- `collect_tools._collect_web_data()` 内部通过 `call_local_api('proxy/{id}', params)` 获取 HTML，再自行解析

```
修改前: collect_tools → urllib.request → 百度 → HTML → parse
修改后: collect_tools → call_local_api('proxy/5') → safe_http_request → 百度 → HTML → parse
```

> **注意**: Baidu Cookie 获取逻辑（`_ensure_baidu_cookies()`）需要迁移到代理处理器中，或作为采集源的预处理步骤保留在 collector 内。

---

外部接口 URL 模板兼容种子数据使用的 `{param}` 与管理界面使用的 `{{param}}` 两种格式；参数替换前统一进行 URL 编码。

> 相关文档：[脚本执行引擎](./03-script-engine.md) | [MCP 注册中心改造](./04-mcp-registry-refactor.md) | [关键集成点](./07-integration-points.md)
