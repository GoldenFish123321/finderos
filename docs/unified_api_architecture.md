# 统一接口驱动架构重构方案 (Unified API-Driven Architecture)

> 文档日期: 2026-07-15  
> 目标版本: 待定（MRP 完成后确定）  
> 前置依赖: `docs/mcp_refactor_plan.md`（MRP）全部 Phase 完成后  
> 基于: DataFinderAgentOS v1.0.0-beta 当前代码  

---

## 〇、与 MRP 的关系

本文档是 `mcp_refactor_plan.md`（MRP）的**远期上层建筑**，不是替代方案。

| 维度 | MRP (待定) | 本文档 (待定) |
|------|-------------|-------------------|
| **核心目标** | MCP 工具数据库驱动 + 管理后台 + 员工权限 | 接口统一管理 + MCP 工具可配置脚本化 |
| **tool_type** | `builtin` / `api` / `crawl4ai` 三分类 | 新增 `script` 型，与现有三分类**共存** |
| **handler_module** | 保留，builtin 型核心机制 | 保留不动；`script` 型作为新增可选路径 |
| **builtin_tools/** | 按分类拆分为子包 | 保留不动；额外在 `api_interfaces` 中注册元数据 |
| **api_interfaces 表** | 不修改 | 新增 `interface_type`、`is_system`、`local_handler` 列 |
| **关系** | **先实施**，提供 MCP 基础设施 | **后实施**，基于 MRP 成果向上抽象 |

**实施原则**：MRP 全部 Phase 完成后，代码中已有完整的 MCP 工具注册表、管理后台和权限过滤。本文档在此基础上叠加「接口统一管理」和「脚本化工具」两层能力，**不推翻 MRP 的任何设计决策**。

---

## 一、重构动机

### 1.1 核心问题

当前架构存在两个分离的概念层级，导致概念重叠和维护困难：

| 当前概念 | 职责 | 问题 |
|----------|------|------|
| **MCP 工具** (`mcp_tools`) | 注册工具供 LLM 调用 | `builtin` 型直接调 Python 函数；`api` 型封装 HTTP 请求——两种形态混在一起 |
| **接口管理** (`api_interfaces`) | 管理可复用 HTTP 接口模板 | 仅服务 API 型数字员工，和 MCP 工具没有关联 |
| **内置工具** (`builtin_tools/`) | 实现具体功能的 Python 函数 | 部分工具（如音乐 `_get_random_music`）本质是对外部 HTTP API 的封装，但被标记为 `builtin` 型，管理员无法在界面查看/修改其调用的 API 地址 |

**本质矛盾**：音乐推荐（`api.injahow.cn`）、天气查询等本质就是「调 HTTP API 返回 JSON」。当前 `_get_random_music()` 代码中已是 HTTP 调用，但在数据库中被标为 `tool_type='builtin'`，管理员不可见其 API 地址。天气则做成了 API 型数字员工而非 MCP 工具，未被 LLM Function Calling 统一调度。

### 1.2 重构目标

```
         ┌──────────────────────────────────────────┐
         │      MCP 工具（对 LLM 暴露的能力）          │
         │   = 本地接口数据源 × N + 纯数据转换脚本     │
         │   脚本仅接收本地接口数据，返回字符串         │
         └──────────────┬───────────────────────────┘
                        │ 引用（仅 local）
         ┌──────────────▼───────────────────────────┐
         │      接口管理（统一代理所有出口流量）        │
         │  ┌──────────────────────────────────┐    │
         │  │       本地接口 (local)             │    │
         │  │  · 系统内置函数 (18个，进程内直调)   │    │
         │  │  · 外部 API 代理 (自动包装为 local) │    │
         │  │  · 上层代码只看到 local，感知不到外网 │    │
         │  └──────────────────────────────────┘    │
         │                │                          │
         │    ┌───────────▼───────────┐              │
         │    │  safe_http_request    │ ← 唯一出口   │
         │    │  (DNS Pinning + SSRF) │   所有外网   │
         │    └───────────────────────┘   流量经此   │
         └──────────────────────────────────────────┘
```

**一句话总结**：接口管理是系统**唯一的对外网络出口**。所有外部 API 在接口管理层注册后自动包装为本地接口（虚拟 local handler），对内透明代理。脚本层只能引用本地接口，完全感知不到外网——脚本做纯数据转换，返回字符串作为 MCP 工具结果。

---

## 二、新架构总览

### 2.1 三层模型

```
┌──────────────────────────────────────────────────────────────────┐
│                     Layer 3: MCP 工具层                           │
│  对 LLM 暴露的 Function Calling 工具。                             │
│  每个工具 = [本地接口数据源 × 1..N] + 纯数据转换脚本               │
│  脚本只能引用本地接口，返回字符串（直接作为 MCP text content）      │
├──────────────────────────────────────────────────────────────────┤
│                     Layer 2: 接口管理层（唯一网络出口）             │
│  统一管理所有 API 接口模板，是所有外部 HTTP 流量的唯一出口。        │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │               本地接口 (local) — 上层唯一可见               │    │
│  │  ┌─────────────────────┐  ┌─────────────────────────┐    │    │
│  │  │ 系统内置 (18个)       │  │ 外部代理 (自动注册)       │    │    │
│  │  │ · 进程内函数直调      │  │ · external 接口自动包装   │    │    │
│  │  │ · is_system=1        │  │   为虚拟 local handler   │    │    │
│  │  │ · 如: warehouse/     │  │ · 内部走 safe_http_      │    │    │
│  │  │   search, employee/  │  │   request (DNS Pinning   │    │    │
│  │  │   list, skill/load   │  │   + SSRF + 审计日志)     │    │    │
│  │  └─────────────────────┘  └─────────────────────────┘    │    │
│  └──────────────────────────────────────────────────────────┘    │
│  注意: 瞭望采集、音乐API、员工API调用等所有出站流量均经此层        │
├──────────────────────────────────────────────────────────────────┤
│                     Layer 1: 脚本执行引擎                         │
│  安全执行用户编写的纯数据转换脚本。                                │
│  · 输入: 本地接口返回的 dict (data_sources)                       │
│  · 输出: str — 直接作为 MCP tools/call 的 text content            │
│  · 沙箱: 完全禁止 import / __builtins__ / 网络 / 文件系统         │
│  · 脚本无需（也不能）发起任何外部调用——接口管理层已代理完毕        │
└──────────────────────────────────────────────────────────────────┘
```

### 2.2 数据流

```mermaid
flowchart TD
    LLM["LLM Function Calling"]
    MCP["MCP Server<br/>(tools/call)"]
    TOOL["MCP 工具 (script 型)<br/>data_sources + transform_script"]
    SCRIPT["转换脚本 (纯数据→字符串)<br/>禁止 import / 网络 / 文件"]

    subgraph 接口管理层 [唯一出口]
        LOCAL1["本地接口: warehouse/search<br/>(进程内 DB 查询)"]
        LOCAL2["本地接口: employee/list<br/>(进程内 DB 查询)"]
        PROXY["代理接口: weather_api<br/>(内部 safe_http → 外网)"]
        SAFE["safe_http_request<br/>DNS Pinning + SSRF + 审计"]
    end

    EXT["外部 API<br/>(天气/音乐/翻译/...)"]
    DB["本地数据库"]

    LLM --> MCP --> TOOL --> SCRIPT
    SCRIPT --> LOCAL1 --> DB
    SCRIPT --> LOCAL2 --> DB
    SCRIPT --> PROXY --> SAFE --> EXT
    SCRIPT -->|"返回 str"| MCP

    style SAFE fill:#4CAF50,color:#fff
    style PROXY fill:#2196F3,color:#fff
```

### 2.3 调用流程详解

```
1. LLM 发起 Function Calling → tools/call { name: "get_weather", arguments: {city: "成都"} }
2. MCP Server 查找工具 "get_weather" (tool_type='script')
3. 工具配置:
   data_sources: [
     { interface_id: 5, param_mapping: { city: "city" } }
     // interface_id=5 是 external 接口"天气API"，但已被接口管理层包装为虚拟 local handler
     // 对脚本而言，它和其他本地接口无异，完全不感知外网
   ]
   transform_script: |
     def transform(data_sources):
         w = data_sources[0]["data"]["current"]
         return f"{w['city']}今天{w['desc']}，温度{w['temp']}℃，湿度{w['humidity']}%"
4. 执行:
   a. registry._build_script_tool() 构建 handler
   b. handler 遍历 data_sources，每个都通过 call_local_api() 调用
      - interface_id=5 → 实际触发 safe_http_request("https://api.weather.com/...")
      - DNS Pinning → SSRF 校验 → 审计日志 → 返回 JSON
   c. 所有 data_sources 结果收集完毕后，传入脚本
   d. 脚本 transform() 返回字符串
5. 字符串直接作为 MCP text content 返回给 LLM
```

> **核心安全原则**：脚本层和 MCP 工具层完全感知不到外网。所有外部 HTTP 调用被接口管理层的
> `safe_http_request` 统一代理。可在网络层部署防火墙：**仅允许接口管理服务进程访问外网**。

---

## 三、数据库变更方案

### 3.1 修改表: `api_interfaces` — 新增接口类型

```sql
-- 新增字段
ALTER TABLE api_interfaces ADD COLUMN interface_type TEXT DEFAULT 'external';
-- 'external' = 外部接口（管理员可增删改）
-- 'local'    = 本地接口（系统内置，不可修改/不可删除）

ALTER TABLE api_interfaces ADD COLUMN is_system INTEGER DEFAULT 0;
-- 1 = 系统内置，前端隐藏编辑/删除按钮

ALTER TABLE api_interfaces ADD COLUMN local_handler TEXT DEFAULT '';
-- 本地接口的内部处理器标识，如 'warehouse/search'
-- interface_type='local' 时指向 _LOCAL_HANDLER_MAP 的键
-- interface_type='external' 时留空（系统自动生成虚拟 handler）

ALTER TABLE api_interfaces ADD COLUMN response_content_type TEXT DEFAULT 'json';
-- 响应内容的 MIME 类型提示: 'json' / 'html' / 'text'
-- 'json': safe_http_request 返回后尝试 json.loads（默认）
-- 'html': 跳过 JSON 解析，返回原始 HTML 文本（瞭望采集等场景）
-- 'text': 返回纯文本
```

修改后 `api_interfaces` 表核心字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| name | TEXT UNIQUE | 接口名称 |
| description | TEXT | 描述 |
| **interface_type** | TEXT | `external` / `local` |
| **is_system** | INTEGER | 系统内置 (0/1)，local 型自动为 1 |
| **local_handler** | TEXT | 本地接口处理器路由（external 型留空，由系统自动生成 `proxy/{id}`） |
| **response_content_type** | TEXT | 响应类型：`json`（默认）/ `html` / `text` |
| api_url | TEXT | 外部接口 URL（external 型必填，local 型填 `local://`） |
| api_method | TEXT | HTTP 方法 |
| api_headers | TEXT | 请求头 JSON |
| api_params_template | TEXT | 参数模板 |
| response_render_template | TEXT | 响应渲染模板（可为空，由脚本替代） |
| api_secret | TEXT | 密钥(加密存储) |
| is_enabled | INTEGER | 启用状态 |
| sort_order | INTEGER | 排序 |

### 3.2 修改表: `mcp_tools` — 新增 script 型字段

```sql
-- 新增字段
ALTER TABLE mcp_tools ADD COLUMN data_sources TEXT DEFAULT '[]';
-- JSON 数组，每个元素: { interface_id, param_mapping }
-- 约束: interface_id 只能指向 interface_type='local' 的记录
--       （external 接口在启动时已自动包装为虚拟 local handler）
-- 例: [{"interface_id": 1, "param_mapping": {"city": "city"}}]

ALTER TABLE mcp_tools ADD COLUMN transform_script TEXT DEFAULT '';
-- 自定义 Python 转换脚本（纯数据转换，不能 import，不能访问外网）
-- 脚本签名: def transform(data_sources: list[dict]) -> str

ALTER TABLE mcp_tools ADD COLUMN script_enabled INTEGER DEFAULT 0;
-- 是否启用脚本转换（无脚本时直接透传第一个接口的 data 字段作为字符串）

-- 以下 MRP 字段保留不动（builtin/api/crawl4ai 型继续使用）:
--   handler_module   → builtin 型仍然使用
--   api_url          → api 型仍然使用（远期建议迁移到 api_interfaces）
--   api_method       → 同上
--   api_headers      → 同上
--   tool_type        → 新增 'script' 选项，四种类型共存
```

修改后 `mcp_tools` 表核心字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| name | TEXT UNIQUE | 工具唯一标识 |
| display_name | TEXT | 显示名称 |
| description | TEXT | 工具描述（供 LLM 理解） |
| category | TEXT | 分类 |
| **tool_type** | TEXT | 保留 MRP 三分类 + 新增 `script` 型（共存） |
| **data_sources** | TEXT | JSON 数组：接口数据源配置 |
| **transform_script** | TEXT | 转换脚本（Python 代码） |
| **script_enabled** | INTEGER | 是否启用脚本 |
| input_schema | TEXT | JSON Schema 参数定义 |
| output_schema | TEXT | 输出 Schema |
| is_enabled | INTEGER | 启用/禁用 |
| is_system | INTEGER | 系统内置 |
| sort_order | INTEGER | 排序 |
| config | TEXT | 额外配置 JSON |

### 3.3 迁移策略

```
Phase 1 — 数据迁移（注意 SQLite 限制）:
  1. api_interfaces 表: 放宽 api_url 约束（NOT NULL → DEFAULT ''），新增
     interface_type / is_system / local_handler / response_content_type 列
     （SQLite 不支持 ALTER COLUMN，需建新表→迁移数据→删旧表→重命名，同一事务）
  2. mcp_tools 表: 新增 data_sources / transform_script / script_enabled 列
  3. 现有 external 接口: 回填 interface_type='external', response_content_type='json'
  4. 为 18 个 builtin 函数创建对应的 local 接口记录 (interface_type='local', is_system=1)
  5. 音乐 API 等在 api_interfaces 中创建 external 记录

Phase 2 — 代码重构:
  1. 实现 local_api_client.py: 函数注册表 + _init_local_handlers() +
     _register_external_proxies()（external → 虚拟 local handler）
  2. 实现 local_api_registry.py: 种子数据 + sync_local_api_interfaces()
  3. 实现 script_engine.py: 收紧的 AST 白名单沙箱（禁 import，纯数据转换，返回 str）
  4. 改造 registry.py: _build_tool_from_db_row() 新增 script 分支，所有数据源统一调 call_local_api()

Phase 3 — 前端适配:
  1. 接口管理列表区分 external / local 标签；local 型只读视图
  2. MCP 工具编辑页: tool_type 下拉增加 'script'；条件渲染数据源选择器 + 脚本编辑器
  3. 脚本测试按钮: 输入参数 → 查看各本地接口调用耗时 → 查看脚本字符串输出
```

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

            def _sync_call(params: dict) -> dict:
                """同步 HTTP 调用（在线程池中执行）。"""
                # 1. 构建 URL（替换模板占位符）
                url = iface["api_url"]
                for key, value in params.items():
                    url = url.replace(f"{{{{{key}}}}}", str(value))

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

## 五、脚本执行引擎设计（纯数据转换）

### 5.1 设计目标

- 管理员在 MCP 工具编辑页编写 Python **纯数据转换**脚本
- 脚本**仅接收本地接口返回的数据**（接口管理层已将外部 API 代理为本地接口）
- 脚本**返回字符串**作为 MCP 工具结果，直接映射为 MCP `text content`
- 脚本**不能发起任何外部调用**（无 import、无网络、无文件系统）
- **安全沙箱**：基于收紧的 AST 白名单遍历，防止恶意代码
- 执行超时保护（signal.alarm + 递归深度限制）

### 5.2 安全策略：收紧的 AST 白名单

> ⚠️ **为什么不用关键词黑名单**: `.lower()` 字符串匹配可被 Unicode 同形字（全角字符）、
> 零宽字符、`chr()` 拼接、`getattr(__builtins__, '__im' + 'port__')` 等无数方式绕过。
> 必须基于**语法树（AST）**做结构级校验。

由于脚本不再需要发起任何外部调用（接口管理层已代理），AST 白名单可以**更激进地收紧**：

**完全禁止 `import` / `ImportFrom`**。数据已是 Python dict/list，不需要 `json`/`random`/`re` 等模块。随机抽取等逻辑用内置函数（`len`、`sorted`、切片）替代。

**AST 白名单允许的节点类型**（纯数据转换最小集合）：

```python
_ALLOWED_NODES = {
    # 基础结构
    ast.Module, ast.FunctionDef, ast.Return,
    ast.Expr, ast.Call, ast.Name, ast.Load, ast.Store,
    ast.Constant,  # Python 3.8+ (str, int, float, bool, None)
    ast.Dict, ast.List, ast.Tuple, ast.Set,
    ast.DictComp, ast.ListComp,
    # 数据访问
    ast.Subscript, ast.Slice,
    # 控制流
    ast.If, ast.IfExp, ast.For, ast.Break, ast.Continue,
    # 运算符
    ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare,
    # 属性访问（限制危险属性名）
    ast.Attribute, ast.keyword, ast.arg, ast.arguments,
    # 变量
    ast.Assign, ast.AugAssign, ast.Pass,
    # 字符串格式化（f-string）
    ast.JoinedStr, ast.FormattedValue,
    # 操作符节点
    ast.And, ast.Or, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod,
    ast.Pow, ast.FloorDiv,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.Is, ast.IsNot, ast.In, ast.NotIn,
    ast.Not, ast.Invert, ast.UAdd, ast.USub,
}
```

**严格禁止**：
- ❌ **所有 `import` / `ImportFrom`** — 脚本不需要任何外部模块
- ❌ `ast.Call` 中调用 `exec`/`eval`/`open`/`getattr`/`setattr`/`__import__`
- ❌ 任何 `ast.Attribute` 链上访问 `__class__`/`__bases__`/`__subclasses__`/`__globals__`/`__code__`/`__closure__`
- ❌ `ast.While` — 纯数据处理不需要无限循环（用 `for` 即可）

### 5.3 脚本接口规范

```python
# 脚本必须定义 transform 函数
# 输入: data_sources — list[dict], 按 data_sources 配置顺序传入每个本地接口的返回
# 输出: str — 直接作为 MCP tools/call 的 text content 返回给 LLM

def transform(data_sources):
    """
    Args:
        data_sources: [
            { "success": True, "data": {...} },   # 本地接口1返回
            { "success": True, "data": {...} },   # 本地接口2返回 (如有)
        ]
    Returns:
        str: 返回给 LLM 的文本结果（直接映射为 MCP text content）
    """
    # 用户在此编写纯数据转换逻辑
    pass
```

> **为什么返回 `str` 而不是 `dict`**: MCP 协议的 `tools/call` 返回 `{content: [{type: "text", text: "..."}]}`。
> 返回字符串直接填入 `text` 字段，无需再 `json.dumps` 包装。LLM 擅长理解和续写自然语言文本，
> 字符串结果比 JSON 嵌套结构更友好。

### 5.4 脚本执行器（收紧版）

```python
# app/services/script_engine.py (新文件)
"""安全的 Python 脚本执行沙箱 — 纯数据转换，无 import，返回字符串。"""

import ast
import logging
import sys
import signal
from typing import Any, Dict, Tuple

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
# 安全内置函数（纯数据操作，无 I/O）
# ═══════════════════════════════════════════════════════════
_SAFE_BUILTINS = {
    # 基础常量
    "True": True, "False": False, "None": None,
    # 类型转换
    "int": int, "float": float, "str": str, "bool": bool,
    "list": list, "dict": dict, "tuple": tuple, "set": set,
    # 集合/序列操作
    "len": len, "range": range, "enumerate": enumerate, "zip": zip,
    "sorted": sorted, "reversed": reversed,
    "min": min, "max": max, "sum": sum, "abs": abs, "round": round,
    "any": any, "all": all, "isinstance": isinstance,
    # 字符串（仅格式化，不涉及 I/O）
    "format": format,
    # 输出静默（print 无效）
    "print": lambda *a, **kw: None,
    # 全部危险函数覆写为 None
    "__import__": None, "exec": None, "eval": None,
    "open": None, "compile": None, "globals": None, "locals": None,
    "getattr": None, "setattr": None, "delattr": None,
    "__builtins__": None, "__build_class__": None,
    "map": None, "filter": None,  # 禁止函数式遍历（可用推导式替代）
}

# ═══════════════════════════════════════════════════════════
# AST 白名单（收紧版：禁止 import / While）
# ═══════════════════════════════════════════════════════════
_ALLOWED_NODE_TYPES = {
    ast.Module, ast.FunctionDef, ast.Return,
    ast.Expr, ast.Call, ast.Name, ast.Load, ast.Store, ast.Del,
    ast.Constant, ast.Dict, ast.List, ast.Tuple, ast.Set,
    ast.DictComp, ast.ListComp,
    ast.Subscript, ast.Slice,
    ast.If, ast.IfExp, ast.For, ast.Break, ast.Continue,
    ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare,
    ast.Attribute, ast.keyword, ast.arg, ast.arguments,
    ast.Assign, ast.AugAssign, ast.Pass,
    ast.JoinedStr, ast.FormattedValue,
    ast.And, ast.Or, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod,
    ast.Pow, ast.FloorDiv,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.Is, ast.IsNot, ast.In, ast.NotIn,
    ast.Not, ast.Invert, ast.UAdd, ast.USub,
}

_FORBIDDEN_ATTR_NAMES = {
    "__class__", "__bases__", "__subclasses__", "__mro__",
    "__globals__", "__code__", "__closure__", "__func__", "__self__",
    "__builtins__", "__builtin__", "__import__",
}
_FORBIDDEN_CALL_NAMES = {
    "exec", "eval", "open", "compile", "globals", "locals",
    "getattr", "setattr", "delattr", "__import__",
}


class ScriptSecurityError(Exception):
    """脚本安全检查未通过。"""
    pass


def _check_ast_node(node: ast.AST):
    """递归遍历 AST 节点，检查是否在白名单内。"""
    if type(node) not in _ALLOWED_NODE_TYPES:
        raise ScriptSecurityError(
            f"不允许的语法节点: {type(node).__name__} (行 {getattr(node, 'lineno', '?')})"
        )

    # 禁止所有 import
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        raise ScriptSecurityError("脚本不允许 import 任何模块")

    # 禁止 While 循环
    if isinstance(node, ast.While):
        raise ScriptSecurityError("脚本不允许使用 while 循环（用 for 替代）")

    # 检查 Call — 禁止调用 exec/eval/open 等
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name):
            if node.func.id in _FORBIDDEN_CALL_NAMES:
                raise ScriptSecurityError(f"不允许调用函数: {node.func.id}")
        elif isinstance(node.func, ast.Attribute):
            if node.func.attr in _FORBIDDEN_CALL_NAMES:
                raise ScriptSecurityError(f"不允许调用方法: {node.func.attr}")

    # 检查 Attribute — 禁止访问危险属性
    if isinstance(node, ast.Attribute):
        if node.attr in _FORBIDDEN_ATTR_NAMES:
            raise ScriptSecurityError(f"不允许访问属性: {node.attr}")

    for child in ast.iter_child_nodes(node):
        _check_ast_node(child)


def validate_script(script: str) -> Tuple[bool, str]:
    """预检脚本安全性（AST 级）。返回 (is_safe, error_message)。"""
    if not script or not script.strip():
        return True, ""

    # 1. 语法检查
    try:
        tree = ast.parse(script, filename="<script>")
    except SyntaxError as e:
        return False, f"脚本语法错误: 行 {e.lineno} — {e.msg}"

    # 2. AST 白名单遍历
    try:
        _check_ast_node(tree)
    except ScriptSecurityError as e:
        return False, str(e)

    # 3. 检查必须定义 transform 函数
    has_transform = any(
        isinstance(node, ast.FunctionDef) and node.name == "transform"
        for node in ast.walk(tree)
    )
    if not has_transform:
        return False, "脚本必须定义 transform(data_sources) 函数"

    return True, ""


def execute_transform_script(script: str, data_sources: list,
                             timeout: float = 3.0) -> str:
    """在受限环境中执行转换脚本。

    Args:
        script: Python 脚本字符串
        data_sources: 本地接口数据源返回列表
        timeout: 最大执行时间（秒），默认 3s（纯数据转换很快）

    Returns:
        str — 转换后的文本结果（直接作为 MCP text content）
    """
    is_safe, error = validate_script(script)
    if not is_safe:
        return f"[脚本验证失败] {error}"

    sys.setrecursionlimit(200)  # 数据转换递归深度限制更严格

    try:
        restricted_globals = dict(_SAFE_BUILTINS)
        compiled = compile(script, "<script>", "exec")
        exec(compiled, restricted_globals)

        transform_func = restricted_globals.get("transform")
        if not callable(transform_func):
            return "[脚本错误] 未定义有效的 transform 函数"

        def _run():
            return transform_func(data_sources)

        # 超时保护
        if hasattr(signal, "SIGALRM"):
            old_handler = signal.signal(
                signal.SIGALRM,
                lambda *_: (_ for _ in ()).throw(TimeoutError("脚本执行超时"))
            )
            signal.setitimer(signal.ITIMER_REAL, timeout)
            try:
                result = _run()
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
                signal.signal(signal.SIGALRM, old_handler)
        else:
            result = _run()

        # 确保返回字符串
        if not isinstance(result, str):
            result = str(result)

        return result

    except TimeoutError:
        return f"[脚本超时] 执行超过 {timeout} 秒"
    except Exception as e:
        logger.error(f"脚本执行失败: {e}", exc_info=True)
        return f"[脚本错误] {str(e)}"
```

> **设计要点**：约 130 行代码。不设 `import` 白名单（脚本无需任何模块）。
> 内置函数限定为纯数据类型转换和集合操作。递归深度限制 200，超时 3 秒。
> 返回值统一为 `str`，直接映射到 MCP text content。"

### 5.5 脚本示例

#### 示例 1: 天气格式化（单个代理接口 + 纯格式化）

```python
# data_sources: [代理接口 "天气API" → safe_http_request → 外部天气服务]
# 脚本只看到本地接口返回的 dict，完全感知不到外网
def transform(data_sources):
    w = data_sources[0]["data"]["current"]
    return f"{w['city']}今天{w['desc']}，温度{w['temp']}℃，湿度{w['humidity']}%，{w['wind']}"
```

#### 示例 2: 数据仓库概览（多个本地接口 + 文本组合）

```python
# data_sources: [warehouse/stats, warehouse/recent]
# 脚本纯本地数据拼接，无 import、无外网
def transform(data_sources):
    stats = data_sources[0]["data"]
    recent = data_sources[1]["data"].get("items", [])

    lines = [
        f"数据仓库概览：",
        f"· 总记录数: {stats.get('total', 0)}",
        f"· 深度采集: {stats.get('deep_collected', 0)}",
        f"· TOP 来源: {', '.join(stats.get('top_sources', [])[:5])}",
        f"",
        f"最近更新:",
    ]
    for item in recent[:5]:
        lines.append(f"· {item.get('title', '无标题')} ({item.get('source_name', '未知')})")

    return "\n".join(lines)
```

#### 示例 3: 随机音乐（代理接口 + 内置随机抽取，无 import）

```python
# data_sources: [代理接口 "网易云热歌榜" → safe_http_request → api.injahow.cn]
# 不使用 import random，改用 hash + 取模实现伪随机抽取
def transform(data_sources):
    songs = data_sources[0].get("data", [])
    if not songs:
        return "暂无歌曲推荐"

    # 用 len 和 id 组合做伪随机（无需 import random）
    idx = sum(ord(c) for c in songs[0].get("name", "")) % len(songs)
    song = songs[idx]

    return f"🎵 推荐歌曲: {song.get('name', '未知')} — {song.get('artist', '未知')}\n来源: 网易云音乐热歌榜"
```

> **注意**: 示例 3 中脚本不需要也没有 `import random`——AST 白名单禁止所有 import。
> 伪随机用 `hash` 或字符编码求和取模替代。如果确实需要真随机，可在 `_SAFE_BUILTINS` 中注入
> `"random_choice": lambda seq: random.choice(seq)`（预先导入好 `random`，不暴露 `import`）。

---

## 六、MCP 工具注册中心改造

### 6.1 新旧对比

| 维度 | 旧架构 (v0.10, MRP 保持) | 新增能力 |
|------|--------------------------|-------------------|
| 工具类型 | `builtin` / `api` / `crawl4ai` | 新增 `script` 型（与三种旧类型**共存**） |
| builtin 型 | Python 函数指针 (`handler_module`) → importlib 加载 | **保持不动** |
| api 型 | `api_url` + `api_headers` → 直接 HTTP 调用 | **远期建议迁移到 api_interfaces 代理模式** |
| script 型 | 不存在 | `data_sources`（仅引用 local 接口，含代理外部API）+ `transform_script`（纯数据→字符串） |
| 音乐工具 | `builtin` 型（代码中硬编码 `api.injahow.cn`） | 可选迁移为 script 型：在 api_interfaces 注册 external → 自动代理为 local → 脚本格式化 |
| 天气工具 | API 型数字员工 | 可选新增 script 型 MCP 工具（同上代理模式） |
| 瞭望采集 | `builtin` 型（直接 urllib.request） | 迁移为：采集源注册为 external 接口 → 自动代理为 local → collect_tools 调 call_local_api 获取 HTML → 自行解析 |
| 注册方式 | MRP 统一的 `_build_tool_from_db_row` → 按 tool_type 分支 | 新增 `script` 分支，所有数据源调 `call_local_api()`（统一 local 接口） |
| 热重载 | 重新读数据库 + importlib | script 型仅需重新读数据库（脚本和接口配置都在 DB 中） |

### 6.2 新 Registry — `_build_tool_from_db_row()` 增加 `script` 分支

```python
# app/mcp/registry.py — 在现有 _build_tool_from_db_row 中新增 script 分支

def _build_tool_from_db_row(row: Dict[str, Any]) -> Optional[MCPTool]:
    """从数据库行构建 MCPTool。新增 script 型分支。"""
    import json

    tool_type = row.get("tool_type", "builtin")

    # ── 新增分支: script 型 ──
    if tool_type == "script":
        return _build_script_tool(row)

    # ── 以下为 MRP 原有逻辑（保持不变）──
    if tool_type == "builtin":
        return _build_builtin_tool(row)       # handler_module + importlib
    elif tool_type == "api":
        return _build_api_tool(row)            # api_url + urllib
    elif tool_type == "crawl4ai":
        return _build_crawl4ai_tool(row)

    return None


def _build_script_tool(row: Dict[str, Any]) -> Optional[MCPTool]:
    """构建 script 型工具: 本地接口数据源 + 纯数据转换脚本。

    关键约束:
    - data_sources 中的 interface_id 只能指向 interface_type='local' 的记录
      （external 接口已在启动时自动包装为虚拟 local handler，见 §4.5）
    - 所有数据源统一通过 call_local_api() 调用，不区分内外
    - 脚本返回字符串，直接作为 MCP text content
    """
    import json
    from app.services.script_engine import execute_transform_script
    from app.services.local_api_client import call_local_api

    try:
        input_schema = json.loads(row.get("input_schema", "{}"))
        data_sources = json.loads(row.get("data_sources", "[]"))
    except (json.JSONDecodeError, TypeError):
        input_schema = {}
        data_sources = []

    transform_script = row.get("transform_script", "")
    script_enabled = bool(row.get("script_enabled", 0))

    if not data_sources:
        logger.warning(f"script 型工具 {row['name']} 未配置 data_sources")
        return None

    async def script_handler(**kwargs) -> str:
        """script 型统一处理器: 调用本地接口 → 脚本转换 → 返回字符串。"""
        # 1. 逐个调用数据源接口（全部走 local_api_client）
        results = []
        for ds in data_sources:
            interface_id = ds.get("interface_id")
            param_mapping = ds.get("param_mapping", {})

            # 映射参数: tool参数名 → 接口参数名
            mapped_params = {}
            for tool_param, iface_param in param_mapping.items():
                if tool_param in kwargs:
                    mapped_params[iface_param] = kwargs[tool_param]
            # 注入上下文变量 ($ctx.*)
            mapped_params = _inject_context_params(mapped_params)

            # 统一通过 local_handler 调用（无论原始是 local 还是 external 代理）
            from app.models.api_interface import ApiInterfaceRepository
            iface = ApiInterfaceRepository.get_by_id(interface_id)
            if not iface:
                results.append({"success": False, "error": f"接口 {interface_id} 不存在"})
                continue

            handler_key = iface.get("local_handler", "")
            if not handler_key:
                results.append({"success": False, "error": f"接口 {interface_id} 无 local_handler"})
                continue

            result = await call_local_api(handler_key, mapped_params)
            results.append(result)

        # 2. 如果启用脚本，执行纯数据转换（返回 str）
        if script_enabled and transform_script.strip():
            return execute_transform_script(transform_script, results)

        # 3. 无脚本时，透传第一个数据源的 data 字段的字符串表示
        first = results[0] if results else {}
        data = first.get("data", first)
        return str(data) if not isinstance(data, str) else data

    return MCPTool(
        name=row["name"],
        description=row.get("description", ""),
        input_schema=input_schema,
        handler=script_handler,  # 返回 str，MCPServer.call_tool 自动包装为 text content
    )


def _inject_context_params(params: dict) -> dict:
    """注入上下文变量。将 $ctx.username 等占位符替换为当前会话上下文值。"""
    from app.mcp.client import _mcp_context_var
    ctx = _mcp_context_var.get() or {}
    resolved = {}
    for key, value in params.items():
        if isinstance(value, str) and value.startswith("$ctx."):
            ctx_key = value[5:]  # 去掉 '$ctx.' 前缀
            resolved[key] = ctx.get(ctx_key, "")
        else:
            resolved[key] = value
    return resolved


### 6.3 本地接口调用客户端

已在 §4.3 中完整定义。`call_local_api(handler_key, params)` 基于 `_LOCAL_HANDLER_MAP` 函数注册表，
通过进程内函数直调实现，零网络开销。`handler_key` 对应 `api_interfaces.local_handler` 字段。
详细代码见 §4.3。

---

## 七、前端管理界面设计

### 7.1 接口管理列表页 — 增加类型区分

```
┌──────────────────────────────────────────────────────────────────┐
│  🔌 接口管理                                    [+ 新增外部接口]   │
├──────────────────────────────────────────────────────────────────┤
│  [全部] [外部接口] [本地接口]  🔍 搜索...                       │
├──────────────────────────────────────────────────────────────────┤
│  ┌────────────────────────────────────────────────────────────┐   │
│  │ 🌐 天气查询接口                                    [外部] │   │
│  │ 查询指定城市的实时天气信息                                   │   │
│  │ GET https://api.weather.com/v1/current                    │   │
│  │ [✏️编辑] [🧪测试] [⏸禁用] [🗑删除]                          │   │
│  └────────────────────────────────────────────────────────────┘   │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │ 🏠 数据仓库搜索                                    [本地] │   │  ← 无编辑/删除按钮
│  │ 在数据仓库中搜索关键词相关内容                                │   │
│  │ 函数: warehouse/search (进程内直调)                         │   │
│  │ [🧪测试] [⏸禁用]                           🔒 系统内置      │   │
│  └────────────────────────────────────────────────────────────┘   │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │ 🏠 数字员工列表                                    [本地] │   │
│  │ 列出所有启用的数字员工                                       │   │
│  │ 函数: employee/list (进程内直调)                            │   │
│  │ [🧪测试] [⏸禁用]                           🔒 系统内置      │   │
│  └────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

### 7.2 MCP 工具编辑页 — 数据源配置（仅本地接口） + 脚本编辑器（字符串输出）

```
┌──────────────────────────────────────────────────────────────────┐
│  ✏️ 编辑 MCP 工具: get_weather                                  │
├──────────────────────────────────────────────────────────────────┤
│  名称:        [get_weather____________]                           │
│  显示名称:    [天气查询_______________]                            │
│  描述:        [查询指定城市的实时天气信息_________________________]  │
│  分类:        [🎵 娱乐 ▼]                                        │
│                                                                  │
│  ── 数据源配置 ──────────────────────────────────────            │
│  ┌─────────────────────────────────────────────────────┐         │
│  │ 数据源 #1                                    [✕ 删除] │         │
│  │ 接口:  [天气查询 (本地代理) ▼]                        │         │
│  │        (原始 external 接口，已自动代理为 local)        │         │
│  │ 参数映射:                                              │         │
│  │   工具参数 city  →  接口参数 city                     │         │
│  │   [+ 添加映射]                                        │         │
│  └─────────────────────────────────────────────────────┘         │
│  ┌─────────────────────────────────────────────────────┐         │
│  │ 数据源 #2                                    [✕ 删除] │         │
│  │ 接口:  [数据仓库搜索 (系统内置) ▼]                    │         │
│  │ 参数映射:                                              │         │
│  │   工具参数 keyword  →  接口参数 keyword               │         │
│  └─────────────────────────────────────────────────────┘         │
│  [+ 添加数据源] （下拉仅列出 local 接口，含代理）                 │
│                                                                  │
│  ── 转换脚本 ────────────────────────────────────────            │
│  ☑ 启用自定义转换脚本（纯数据 → 字符串）                          │
│  ┌─────────────────────────────────────────────────────┐         │
│  │ def transform(data_sources):                         │         │
│  │     w = data_sources[0]["data"]["current"]           │         │
│  │     return f"{w['city']}今天{w['desc']}，"           │         │
│  │            f"温度{w['temp']}℃"                       │         │
│  └─────────────────────────────────────────────────────┘         │
│  [🧪 测试脚本]  [📋 脚本模板]                                    │
│                                                                  │
│  ── 参数 Schema ─────────────────────────────────────            │
│  { "type": "object", "properties": { "city": {"type": "string"} }│
│                                                                  │
│  [💾 保存]  [🧪 在线测试]  [↩ 返回]                              │
└──────────────────────────────────────────────────────────────────┘
```

### 7.3 接口管理编辑页 — 增加本地接口只读视图

```
┌──────────────────────────────────────────────────────────────────┐
│  🔒 查看本地接口: 数据仓库搜索 (系统内置，不可编辑)                │
├──────────────────────────────────────────────────────────────────┤
│  名称:        数据仓库搜索                                        │
│  描述:        在数据仓库中搜索关键词相关内容                        │
│  类型:        🏠 本地接口 (系统内置)                              │
│  处理器:      warehouse/search (进程内函数直调)                   │
│  参数模板:    { "keyword": "{{keyword}}", "limit": 10 }         │
│                                                                  │
│  ⚠️ 此为系统内置本地接口，不可修改。如需自定义行为，请在此基础上   │
│     创建 MCP 工具（script 型）并使用转换脚本。                     │
│                                                                  │
│  [🧪 测试]  [↩ 返回]                                            │
└──────────────────────────────────────────────────────────────────┘
```

---

## 八、文件变更清单

### 8.1 新建文件

```
finderos/app/
├── services/
│   ├── script_engine.py            # 脚本执行沙箱引擎（AST 白名单）
│   ├── local_api_client.py         # 本地接口函数注册表 + 进程内调用
│   └── local_api_registry.py       # 本地接口元数据自动同步到 api_interfaces
├── templates/admin/
│   └── script_templates.html       # 脚本模板片段
└── static/js/
    └── mcp_script_editor.js        # 脚本编辑器前端（语法高亮、自动补全、测试）

finderos/docs/
└── unified_api_architecture.md     # 本文档
```

### 8.2 修改文件

```
✏️ app/models/db.py                 # api_interfaces: 加 interface_type/is_system/local_handler/
                                    #   response_content_type 列；api_url 从 NOT NULL → DEFAULT ''
                                    # mcp_tools: 加 data_sources/transform_script/script_enabled 列
✏️ app/models/api_interface.py     # 新增字段 CRUD；get_enabled_external() 查询方法
✏️ app/models/mcp_tool.py          # 新增 data_sources/transform_script/script_enabled CRUD
✏️ app/mcp/registry.py             # _build_tool_from_db_row(): 新增 script 型分支
                                    #   builtin/api/crawl4ai 分支保持不变（MRP 兼容）
                                    #   script 型所有数据源统一调 call_local_api()
✏️ app/controllers/admin_interface.py  # 列表: interface_type 列 + external/local Tab
                                    # 表单: local 型只读视图；external 型增加 response_content_type 选择
✏️ app/controllers/admin_mcp.py    # 表单: tool_type 下拉增加 'script' 选项
                                    # 条件显示 data_sources 配置区（仅限 local 接口） + 脚本编辑器
✏️ app/templates/admin/interface_list.html    # 区分 external/local 标签
✏️ app/templates/admin/interface_form.html    # local 型只读视图；external 型含 response_content_type
✏️ app/templates/admin/mcp_tool_form.html     # 数据源选择器（仅列 local 接口） + 脚本编辑器
✏️ main.py                         # 启动顺序: _init_local_handlers → sync → _register_external_proxies → load_all_from_db
✏️ migrate_db.py                   # 迁移脚本（含 api_url 约束放宽 + 新增4列）
✏️ seed data (db.py)               # 初始化 18 个本地接口种子数据 + script 型工具示例
✏️ app/mcp/builtin_tools/          # 远期: music/collect/employee 等含外部 HTTP 的工具迁移到代理模式
```


---

## 九、关键集成点适配

### 9.1 user_chat.py — SSE 流式对话适配

`user_chat.py` 有两条 MCP 调用路径，script 型工具无需特殊适配即可正常工作：

| 路径 | 当前行为 | script 型兼容性 |
|------|---------|----------------|
| **路径 A**: `_chat_with_llm_tools()` | LLM Function Calling → `MCPClient.get_openai_tools()` → 多轮 tool_calls | ✅ 兼容。`MCPTool.call()` 对 script 型的 `script_handler`（返回 str）与 builtin 型行为一致 |
| **路径 B**: `_chat_with_mcp_fallback()` | 无 API Key 语义匹配 → `MCPClient.match_tool_by_query()` | ✅ 兼容。语义匹配基于 `description` 字段，不关心 tool_type |
| **@员工调用**: `UserEmployeeInvokeHandler` | 按 `mcp_tool_ids` 过滤 → `match_tool_by_query(message, emp_id)` | ✅ 兼容。权限过滤在 MCP 工具层面，不在接口层面 |

**需注意的点**：
- script 型工具的数据源可能涉及外部 HTTP（经 `safe_http_request` 代理），耗时可能 >5s。LLM Function Calling 的 tool_calls 超时需适当放宽。
- 建议在 SSE 流中增加 `event: tool_progress` 事件，告知用户「正在查询数据…」「正在分析…」等中间状态。

### 9.2 LLM API 调用 — 唯一例外

`user_chat.py` 中的 `_call_llm_api_sync()` 调用 OpenAI 兼容 API（Chat Completions）。这类调用**不走接口管理代理**，原因：

1. LLM API 的协议（Chat Completions + SSE streaming）与通用 HTTP 接口模板不兼容
2. `api_base` 已在 `models` 表中由管理员显式配置
3. 流式响应需要长连接保持，不适合通用的请求-响应模板

**安全加固方案**（不改变调用路径，但加防护）：
```python
# user_chat.py — 在 _call_llm_api_sync() 调用前:
from app.utils.security import validate_url_safe
if not validate_url_safe(api_base)[0]:
    raise SafeHttpError(f"LLM API URL 不安全: {api_base}")
```
或者远期将 LLM API 调用也迁移为使用 `safe_http_request` 的 DNS Pinning 连接模式（需要扩展 `safe_http_request` 支持 streaming）。

### 9.3 员工工具权限过滤

权限过滤沿用 MRP 机制：`digital_employees.mcp_tool_ids` JSON 数组决定员工可使用哪些工具。
script 型工具与 builtin 型在权限过滤上**无区别**——都在 MCP 工具层面控制。

接口层（`api_interfaces`）是共享资源，不参与员工权限过滤。即：员工 A 和员工 B 都可以使用引用同一接口的不同 MCP 工具。这是合理的——接口只是数据源，权限由「谁能调用哪个 MCP 工具」决定。

### 9.4 上下文注入

`MCPClient._inject_context()` 向工具注入 `username` 等会话上下文。script 型工具的 `_inject_context_params()` 支持 `$ctx.username` 等占位符语法：

```json
// data_sources param_mapping 示例
{
  "interface_id": 10,
  "param_mapping": {
    "username": "$ctx.username",
    "keyword": "keyword"
  }
}
```

该占位符对本地接口和代理接口同样有效。

### 9.5 与 register_all_tools() 的关系

MRP 的 `register_all_tools()` 调用 `MCPToolRegistry.load_all_from_db()`，后者遍历 `mcp_tools` 表中所有 `is_enabled=1` 的记录。新增 `tool_type='script'` 后，`_build_tool_from_db_row` 自动分发到 `_build_script_tool()`——**无需修改 `load_all_from_db` 或 `register_all_tools`**。热重载同样自动覆盖。

### 9.6 网络层防火墙配合

实施本方案后，可在操作系统/容器层面配置出站防火墙规则：

```
# 仅允许接口管理服务进程访问外网
# Windows Firewall / iptables 示例思路:
Allow: python.exe → 0.0.0.0/0:443 (仅 safe_http_request 使用)
Deny:  python.exe → 0.0.0.0/0:*   (其他所有出站)
Deny:  python.exe → 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16 (内网)
```

结合 `safe_http_request` 的 DNS Pinning + SSRF 校验，形成纵深防御。

---

## 十、迁移计划

> **前置条件**: MRP（mcp_refactor_plan.md）全部 Phase 已完成，`mcp_tools` 表、管理后台、员工工具选择器已上线。

### Phase 1: 数据层准备（1天）

| 步骤 | 内容 |
|------|------|
| 1.1 | `api_interfaces` 表：放宽 `api_url` 约束 + 新增 `interface_type`, `is_system`, `local_handler`, `response_content_type` 列 |
| 1.2 | `mcp_tools` 表：新增 `data_sources`, `transform_script`, `script_enabled` 列 |
| 1.3 | 编写迁移脚本 `migrate_db.py` |

### Phase 2: 本地接口注册表 + 外部代理（1.5天）

| 步骤 | 内容 |
|------|------|
| 2.1 | 实现 `local_api_client.py`：函数注册表 + `_init_local_handlers()` + `_register_external_proxies()` + `call_local_api()` |
| 2.2 | 实现 `local_api_registry.py`：18 个种子数据 + `sync_local_api_interfaces()` |
| 2.3 | 在 `main.py` 启动流程中按顺序调用：`_init_local_handlers()` → `sync_local_api_interfaces()` → `_register_external_proxies()` → `load_all_from_db()` |
| 2.4 | 为瞭望采集源、音乐 API 等在 `api_interfaces` 创建 external 记录（含 `response_content_type='html'`） |

### Phase 3: 脚本引擎（1天）

| 步骤 | 内容 |
|------|------|
| 3.1 | 实现 `script_engine.py`：收紧的 AST 白名单校验（禁 import）+ 受限执行（返回 str）+ 超时保护 |
| 3.2 | 实现脚本在线测试 API（`POST /admin/mcp/tool/test-script`） |
| 3.3 | 预置脚本模板（天气格式化、数据概览、音乐推荐等） |

### Phase 4: MCP 注册中心改造（1天）

| 步骤 | 内容 |
|------|------|
| 4.1 | `registry.py`：新增 `_build_script_tool()` —— 所有数据源统一调 `call_local_api()` |
| 4.2 | `_build_tool_from_db_row()`：增加 `if tool_type == 'script'` 分支 |
| 4.3 | 实现 `_inject_context_params()` 上下文注入 |
| 4.4 | 创建示例 script 型工具（天气、音乐），验证端到端代理流程 |

### Phase 5: 前端适配（2天）

| 步骤 | 内容 |
|------|------|
| 5.1 | 接口管理列表：增加 external/local Tab + 类型徽章 |
| 5.2 | 接口表单：local 型只读视图；external 型增加 response_content_type 选择 |
| 5.3 | MCP 工具表单：tool_type 下拉新增 `script`；数据源选择器（仅列 local 接口，含代理） + 脚本编辑器 |
| 5.4 | 脚本编辑器：textarea + 语法高亮（可选 CodeMirror） |
| 5.5 | 脚本测试按钮：输入参数 → 查看本地接口调用耗时 → 查看脚本字符串输出 |

### Phase 6: 安全加固 + 文档（1天）

| 步骤 | 内容 |
|------|------|
| 6.1 | `registry.py` 中 `api` 型工具的 `urllib.request.urlopen()` 迁移为 `safe_http_request()` |
| 6.2 | `user_chat.py` 中 LLM API 调用增加 `validate_url_safe()` 前置校验 |
| 6.3 | `entertainment_tools.py` 音乐工具：硬编码 URL 迁移到 `api_interfaces` external 记录 |
| 6.4 | 更新 `docs/design.md`、`docs/api.md`、`README.md` |
| 6.5 | 部署网络层防火墙规则（仅允许 safe_http_request 进程访问外网） |

---

## 十一、兼容策略

```
实施后四种 tool_type 共存:
  - tool_type='builtin':   保持 MRP 的 handler_module + importlib 路径
  - tool_type='api':        保持 MRP 的 api_url + urllib 路径（远期加固为 safe_http_request）
  - tool_type='crawl4ai':   保持 MRP 的爬虫路径
  - tool_type='script':     新增 data_sources（仅 local 接口）+ transform_script（纯数据→str）路径

远期（v0.7.0+）可选迁移:
  - 音乐工具: builtin 版（硬编码 api.injahow.cn）→ 在 api_interfaces 注册 external → 自动代理 → script 型
  - 瞭望采集: builtin 版（直接 urllib.request）→ 采集源注册为 external → call_local_api('proxy/{id}') 获取 HTML
  - API 型员工: 直接 urllib.request → api_interfaces 代理模式
  - builtin_tools/ 目录不删除（MRP 已投入拆分工作，保留价值）
```

---

## 十二、架构收益总结

| 维度 | 收益 |
|------|------|
| **安全出口统一** | 所有外部 HTTP 流量经 `api_interfaces` → `safe_http_request`（DNS Pinning + SSRF + 审计），消除分散出口的 SSRF 风险 |
| **透明代理** | external 接口启动时自动包装为虚拟 local handler，上层代码（MCP 工具、脚本）无需感知内外网区别 |
| **脚本极简化** | 脚本仅做纯数据→字符串转换，禁 import、禁网络、禁文件。AST 沙箱从 ~200 行简化到 ~130 行 |
| **防火墙友好** | 唯一出站进程路径明确，可部署网络层规则：仅允许接口管理服务访问外网 |
| **热重载即时生效** | script 型工具的接口配置和脚本均在数据库中，修改后重载即可，无需重启或改代码 |
| **内部能力复用** | 18 个系统内置 + N 个代理接口全部注册在 `_LOCAL_HANDLER_MAP`，可被任意 script 型工具组合引用 |
| **MCP 协议原生对齐** | 脚本返回 `str`，直接映射为 MCP `text content`，LLM 友好，无需额外 JSON 包装 |

---

> **文档维护**: 本文档随架构重构实施同步更新。
