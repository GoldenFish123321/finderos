# 数字员工 & MCP 重构方案

> 文档日期: 2026-07-15
> 目标版本: 待定（merge 时确定）
> 基于: DataFinderAgentOS 当前版本

---

## 一、现状分析

### 1.1 当前架构总览

```
┌──────────────────────────────────────────────────────────────┐
│  app/mcp/ (MCP 模块)                                          │
│  ├── server.py   — MCP Server 单例 + 工具注册/发现/调用        │
│  ├── client.py   — MCP Client (OpenAI 格式转换 + 语义匹配)     │
│  └── tools.py    — 10 个工具定义 + register_all_tools()       │
├──────────────────────────────────────────────────────────────┤
│  app/models/                                                  │
│  ├── digital_employee.py  — 数字员工 CRUD (LLM型/API型)        │
│  └── skill.py             — 技能库 CRUD (prompt/function型)    │
├──────────────────────────────────────────────────────────────┤
│  app/controllers/                                             │
│  ├── user_chat.py        — 前台对话 (SSE + MCP调用)            │
│  ├── admin_employee.py   — 员工管理后台                        │
│  └── admin_skill.py      — 技能管理后台                        │
├──────────────────────────────────────────────────────────────┤
│  app/services/                                                │
│  ├── collector.py         — 网页采集引擎 (urllib + 正则)       │
│  └── deep_collector.py    — 深度采集 (正文提取 + crawl4ai可选)  │
└──────────────────────────────────────────────────────────────┘
```

### 1.2 当前问题清单

| # | 问题 | 详情 |
|---|------|------|
| 1 | **MCP 工具覆盖不全** | 只有 10 个工具（数据仓库3 + 采集2 + 员工1 + 音乐1 + 对话2 + 技能1），大量 CRUD API 未封装为 MCP 工具 |
| 2 | **MCP 工具无管理界面** | 无法启用/禁用单个工具，无法在线测试，无可视化配置 |
| 3 | **数字员工与MCP割裂** | 员工编辑页只选 skills（prompt模板/function映射），无法直接选择可使用哪些 MCP 工具 |
| 4 | **TAG 系统混乱** | 种子数据中的 `skills` 字段存的是中文标签字符串（如 `["信息检索", "数据分析", "文案撰写", "代码辅助"]`），这些既不是 skill 也不是 mcp tool，仅是显示标签 |
| 5 | **Crawl4ai 是硬编码开关** | `crawl4ai_enabled` 是 `digital_employees` 表的一个布尔字段 + 表单复选框，不是标准 MCP 工具 |
| 6 | **API 型员工未 MCP 化** | API 型员工（如天气）直接 HTTP 调用，未走 MCP 协议，无法被 LLM Function Calling 统一调度 |
| 7 | **Skill 与 MCP Tool 概念重叠** | `function` 型 skill 本质上就是 MCP Tool 的别名映射，存在两层抽象 |

### 1.3 当前数据模型关键字段

**digital_employees 表**:
```sql
skills              TEXT DEFAULT '[]'   -- JSON数组：旧格式存字符串标签["信息检索","数据分析"]
                                        -- 新格式存技能ID数组[1,2,3]
crawl4ai_enabled    INTEGER DEFAULT 0   -- Crawl4ai开关（硬编码）
```

**skills 表**:
```sql
skill_type          TEXT    -- 'prompt' 或 'function'
function_name       TEXT    -- 映射的 MCP 工具名 (如 'search_warehouse')
function_params     TEXT    -- 默认参数 JSON
prompt_template     TEXT    -- prompt 增强模板
```

---

## 二、重构目标

### 2.1 核心原则

1. **一切皆 MCP Tool**：所有系统能力（采集、搜索、CRUD、外部API、crawl4ai等）统一封装为 MCP 工具
2. **Skill = MCP Tool + Prompt 增强**：Skill 统一为 "带 Prompt 模板的 MCP 工具包装"，消除概念重叠
3. **数字员工 = 角色 + MCP工具集 + 系统提示词**：员工的能力由其可使用的 MCP 工具集合决定
4. **TAG 可视化为 MCP/Skill 徽章**：前端展示用不同颜色区分 MCP 工具（蓝色）、Skill（绿色）和旧 TAG（橙黄色，保持现有风格）
5. **管理界面化**：MCP 工具可管理、可测试、可配置

### 2.2 目标架构

```
┌──────────────────────────────────────────────────────────────────┐
│                        MCP Tool Registry (数据库驱动)              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐             │
│  │ 数据仓库  │ │ 瞭望采集  │ │ 深度采集  │ │ 员工管理  │  ...20+工具 │
│  │ 搜索/统计 │ │ 关键词采集│ │ URL抓取   │ │ 列表/调用 │             │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐             │
│  │ AI模型   │ │ 对话管理  │ │ 音乐娱乐  │ │ Crawl4ai │             │
│  │ 列表/切换│ │ 历史/消息 │ │ 随机推荐  │ │ 智能爬取  │             │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘             │
├──────────────────────────────────────────────────────────────────┤
│                        Skill Registry                             │
│  ┌──────────────────────────────────────────────────────┐        │
│  │ Skill = MCP Tool引用 + Prompt模板 + 默认参数 + 描述    │        │
│  │ 统一为一种类型，不再区分 prompt/function               │        │
│  └──────────────────────────────────────────────────────┘        │
├──────────────────────────────────────────────────────────────────┤
│                      Digital Employee                             │
│  ┌──────────────────────────────────────────────────────┐        │
│  │ 员工 = 名称 + 类型(llm/api/mcp) + 模型 + SystemPrompt │        │
│  │       + [mcp_tool_ids] + [skills: Skill ID数组]       │        │
│  └──────────────────────────────────────────────────────┘        │
└──────────────────────────────────────────────────────────────────┘
```

---

## 三、数据库变更方案

> 实现说明：原计划中的 `skill_ids_new` 未单独建列。实际实现复用了历史
> `digital_employees.skills` 列，并将其数据从字符串标签迁移为 Skill ID JSON 数组；
> 这是当前正式数据契约。

### 3.1 新增表: `mcp_tools`

```sql
CREATE TABLE mcp_tools (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT UNIQUE NOT NULL,         -- 工具唯一标识: search_warehouse
    display_name    TEXT NOT NULL,                -- 显示名称: 数据仓库搜索
    description     TEXT DEFAULT '',              -- 工具描述 (供LLM理解)
    category        TEXT DEFAULT 'general',       -- 分类: warehouse/collect/employee/model/chat/entertainment
    tool_type       TEXT DEFAULT 'builtin',       -- builtin / api / crawl4ai
    -- builtin 型: 系统内置Python函数
    handler_module  TEXT DEFAULT '',              -- 处理模块路径: app.mcp.tools._search_warehouse
    -- api 型: HTTP API 封装
    api_url         TEXT DEFAULT '',              -- API URL 模板
    api_method      TEXT DEFAULT 'GET',           -- GET/POST
    api_headers     TEXT DEFAULT '{}',            -- 请求头 JSON
    api_params_template TEXT DEFAULT '',          -- 参数模板
    -- 通用
    input_schema    TEXT DEFAULT '{}',            -- JSON Schema 参数定义
    output_schema   TEXT DEFAULT '{}',            -- 输出 Schema (可选)
    is_enabled      INTEGER DEFAULT 1,            -- 启用/禁用
    is_system       INTEGER DEFAULT 0,            -- 系统内置 (不可删除)
    sort_order      INTEGER DEFAULT 0,            -- 排序
    config          TEXT DEFAULT '{}',            -- 额外配置 JSON
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 3.2 修改表: `skills` (简化)

```sql
-- 移除 function_name, function_params 字段
-- 新增 mcp_tool_id 外键关联

-- 迁移方式: 新建表 + 数据迁移，或 ALTER TABLE 添加列
ALTER TABLE skills ADD COLUMN mcp_tool_id INTEGER DEFAULT NULL
    REFERENCES mcp_tools(id) ON DELETE SET NULL;

-- 后续版本可废弃 function_name / function_params（保留兼容读取）
-- (保留兼容读取，不再使用)
```

修改后 skills 表核心字段：
```sql
id              INTEGER PRIMARY KEY
name            TEXT UNIQUE      -- 技能名称
description     TEXT             -- 技能描述
mcp_tool_id     INTEGER          -- 关联的 MCP 工具 (可为NULL表示纯prompt)
prompt_template TEXT             -- Prompt 增强模板
default_params  TEXT DEFAULT '{}'-- 默认参数 JSON
is_enabled      INTEGER DEFAULT 1
```

### 3.3 修改表: `digital_employees`

```sql
-- 旧字段 (保留兼容，标记废弃):
--   skills TEXT DEFAULT '[]'       → 改存 skill_ids JSON数组
--   crawl4ai_enabled INTEGER       → 废弃，改为通过 mcp_tool_ids 控制

-- 新增字段:
ALTER TABLE digital_employees ADD COLUMN mcp_tool_ids TEXT DEFAULT '[]';
-- 存储格式: JSON 数组 [1,2,3,5] 对应 mcp_tools.id

ALTER TABLE digital_employees ADD COLUMN skill_ids_new TEXT DEFAULT '[]';
-- 兼容旧 skills 字段，新数据存这里 (技能ID数组)

-- 将旧的 crawl4ai_enabled 标记为废弃 (保留列但不再使用)
```

### 3.4 新增表: `mcp_tool_test_logs`

```sql
CREATE TABLE mcp_tool_test_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_id         INTEGER NOT NULL,
    test_params     TEXT DEFAULT '{}',       -- 测试参数 JSON
    test_result     TEXT DEFAULT '',         -- 测试结果
    is_success      INTEGER DEFAULT 0,       -- 是否成功
    duration_ms     INTEGER DEFAULT 0,       -- 耗时毫秒
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tool_id) REFERENCES mcp_tools(id) ON DELETE CASCADE
);
```

---

## 四、MCP 工具清单（完整版）

### 4.1 工具分类体系

| 分类 | 标识 | 颜色 | 说明 |
|------|------|------|------|
| 🔍 数据仓库 | `warehouse` | 蓝色 `#5EA3FF` | 数据查询、搜索、统计 |
| 🔭 瞭望采集 | `collect` | 绿色 `#5FB878` | Web 采集、深度抓取 |
| 🤖 数字员工 | `employee` | 紫色 `#A855F7` | 员工列表、调用 |
| 🧠 AI 模型 | `model` | 青色 `#06B6D4` | 模型列表、对话管理 |
| 💬 对话管理 | `chat` | 粉色 `#EC4899` | 对话历史、消息 |
| 🎵 娱乐 | `entertainment` | 橙色 `#FFB800` | 音乐等 |
| 🕷️ 爬虫增强 | `crawl4ai` | 红色 `#EF4444` | Crawl4ai 深度爬取 |
| 🔧 系统管理 | `system` | 灰色 `#6B7280` | 用户/角色/功能管理 |

### 4.2 完整工具列表（目标: 20+ 工具）

```
现有工具 (10个，需改造):
 1. search_warehouse          🔍 数据仓库搜索
 2. get_recent_warehouse_data 🔍 最新数据
 3. get_warehouse_stats       🔍 数据统计
 4. collect_web_data          🔭 全网采集
 5. deep_collect_url          🔭 深度采集URL
 6. list_digital_employees    🤖 员工列表
 7. get_random_music          🎵 随机音乐
 8. list_conversations        💬 对话历史
 9. get_conversation_messages 💬 对话消息
10. load_skill                🔧 加载技能

新增工具 (12+个):
11. list_ai_models            🧠 AI模型列表
12. get_default_model         🧠 获取默认模型
13. list_watch_sources        🔭 瞭望源列表
14. search_warehouse_fulltext 🔍 全文检索 (FTS5)
15. get_warehouse_by_id       🔍 按ID查数据
16. collect_with_crawl4ai     🕷️ Crawl4ai深度采集
17. batch_deep_collect        🕷️ 批量深度采集
18. list_users                🔧 用户列表 (需admin权限)
19. get_system_stats          🔧 系统统计概览
20. invoke_digital_employee   🤖 调用指定数字员工
21. translate_text            🔧 文本翻译 (skill包装)
```

### 4.3 工具定义示例

```python
# 新增工具: collect_with_crawl4ai (替代旧的 crawl4ai_enabled 复选框)
{
    "name": "collect_with_crawl4ai",
    "display_name": "Crawl4ai 智能采集",
    "description": (
        "使用 Crawl4ai 对指定 URL 进行智能深度采集，支持 JS 渲染页面、"
        "自动提取正文、表格、图片等结构化内容。比普通深度采集更强大。"
        "当用户需要采集 SPN/JS 渲染页面或要求高质量提取时使用。"
    ),
    "category": "crawl4ai",
    "tool_type": "builtin",
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "目标URL"},
            "extract_mode": {"type": "string", "enum": ["auto", "article", "full"], "default": "auto"},
        },
        "required": ["url"],
    },
}

# 新增工具: invoke_digital_employee
{
    "name": "invoke_digital_employee",
    "display_name": "调用数字员工",
    "description": (
        "调用指定的数字员工执行任务。根据员工类型不同："
        "LLM 型员工将使用其绑定的模型和提示词处理任务；"
        "API 型员工将调用其配置的外部 API。"
    ),
    "category": "employee",
    "tool_type": "builtin",
    "input_schema": {
        "type": "object",
        "properties": {
            "employee_name": {"type": "string", "description": "员工名称或ID"},
            "message": {"type": "string", "description": "发送给员工的消息/任务描述"},
        },
        "required": ["employee_name", "message"],
    },
}
```

---

## 五、文件变更清单

### 5.1 新建文件

```
app/
├── models/
│   └── mcp_tool.py              # MCP 工具 Repository (CRUD)
├── controllers/
│   └── admin_mcp.py             # MCP 管理后台 Controller
├── mcp/
│   ├── registry.py              # MCP 工具注册中心 (数据库驱动, 替代 tools.py 硬编码)
│   └── builtin_tools/
│       ├── __init__.py
│       ├── warehouse_tools.py   # 数据仓库类工具实现
│       ├── collect_tools.py     # 采集类工具实现
│       ├── employee_tools.py    # 数字员工类工具实现
│       ├── model_tools.py       # AI模型类工具实现
│       ├── chat_tools.py        # 对话类工具实现
│       ├── crawl4ai_tools.py    # Crawl4ai 工具实现 (从 services 迁移)
│       ├── system_tools.py      # 系统管理类工具实现
│       └── entertainment_tools.py # 娱乐类工具实现
├── templates/
│   └── admin/
│       ├── mcp_tool_list.html   # MCP 工具管理列表页
│       └── mcp_tool_form.html   # MCP 工具配置/测试页
└── static/
    └── js/
        └── mcp_tool_test.js     # 工具测试前端 JS
```

### 5.2 修改文件

```
✏️ app/mcp/__init__.py            # 导出新模块
✏️ app/mcp/server.py              # 支持动态注册/注销工具
✏️ app/mcp/client.py              # 支持工具权限过滤(按员工)
✏️ app/mcp/tools.py               # 重构为 builtin_tools 包 (或保留兼容)
✏️ app/models/db.py               # 新增 mcp_tools 表 + 种子数据
✏️ app/models/digital_employee.py # 新增 mcp_tool_ids 字段
✏️ app/models/skill.py            # 新增 mcp_tool_id 字段
✏️ app/controllers/user_chat.py   # 适配新 MCP 架构
✏️ app/controllers/admin_employee.py # 新增 MCP工具选择器
✏️ app/controllers/admin_skill.py # 适配 skill 关联 MCP 工具
✏️ app/templates/admin/employee_form.html  # 新增 MCP工具多选
✏️ app/templates/admin/employee_list.html  # TAG → MCP/Skill 三色徽章
✏️ app/templates/user_chat.html   # 前端 @员工面板显示工具徽章
✏️ main.py                        # 新增 MCP 管理路由
✏️ migrate_db.py                  # 新增迁移
✏️ docs/design.md                 # 更新设计文档
✏️ docs/api.md                    # 更新 API 文档
```

---

## 六、实施步骤

### Phase 1: 数据层改造 (1-2天)

```
Step 1.1  创建 mcp_tools 表 (migrate_db.py)
Step 1.2  修改 skills 表 (新增 mcp_tool_id 列)
Step 1.3  修改 digital_employees 表 (新增 mcp_tool_ids 列)
Step 1.4  创建 mcp_tool_test_logs 表
Step 1.5  创建 MCPToolRepository (app/models/mcp_tool.py)
Step 1.6  编写种子数据: 将现有 10 个工具 + 新增工具写入 mcp_tools 表
Step 1.7  数据迁移: 将旧 skills JSON 标签 → skill 记录; crawl4ai_enabled → mcp_tool
```

### Phase 2: MCP 核心重构 (2-3天)

```
Step 2.1  创建 app/mcp/registry.py — 数据库驱动的工具注册中心
           - 启动时从 mcp_tools 表加载所有 enabled 工具
           - 动态注册到 MCPServer
           - 支持热重载 (通过管理后台触发)
Step 2.2  拆分 tools.py 为 builtin_tools/ 子包
           - 每个分类一个文件
           - 保持原有 handler 函数不变
Step 2.3  改造 MCPServer:
           - register_tool_from_db() — 从数据库记录创建 MCPTool
           - unregister_tool() — 运行时注销工具
           - reload_tools() — 重新加载
Step 2.4  改造 MCPClient:
           - get_openai_tools_for_employee(emp_id) — 按员工权限过滤
           - 新语义匹配权重算法
```

### Phase 3: MCP 管理后台 (2天)

```
Step 3.1  创建 admin_mcp.py Controller:
           - MCPToolListHandler — 工具列表 (分页/分类筛选/状态筛选)
           - MCPToolFormHandler — 工具配置编辑 (名称/描述/Schema/启用)
           - MCPToolTestHandler — 在线测试 (输入参数 → 执行 → 显示结果)
           - MCPToolToggleHandler — 启用/禁用
           - MCPToolReloadHandler — 热重载所有工具
Step 3.2  创建 mcp_tool_list.html 模板:
           - 按分类 Tab 筛选
           - 卡片或表格布局
           - 每个工具: 名称/描述/类型徽章/启用开关/测试按钮/编辑按钮
Step 3.3  创建 mcp_tool_form.html 模板:
           - 工具信息编辑
           - input_schema JSON 编辑器
           - API 型工具的 URL/Headers 配置
Step 3.4  创建工具测试功能:
           - 参数输入表单 (根据 input_schema 动态生成)
           - 执行结果展示 + 耗时统计
           - 测试日志记录
Step 3.5  注册路由 (main.py):
           /admin/mcp/tool         → MCPToolListHandler
           /admin/mcp/tool/edit    → MCPToolFormHandler
           /admin/mcp/tool/test    → MCPToolTestHandler
           /admin/mcp/tool/toggle  → MCPToolToggleHandler
           /admin/mcp/reload       → MCPToolReloadHandler
```

### Phase 4: 数字员工改造 (1-2天)

```
Step 4.1  改造 employee_form.html:
           - 新增「MCP 工具」多选区域 (分类折叠，复选框)
           - 新增「Skill」多选区域 (保持现有，但改为关联 MCP 工具)
           - 移除 crawl4ai_enabled 复选框 (改为通过选择 collect_with_crawl4ai 工具实现)
Step 4.2  改造 admin_employee.py:
           - 保存时解析 mcp_tool_ids (JSON数组)
           - 读取时返回工具详情列表 (供模板渲染)
Step 4.3  改造 employee_list.html 卡片:
           - MCP工具: 蓝色圆角徽章 (.mcp-tag)
           - Skill: 绿色圆角徽章 (.skill-tag)
           - 旧TAG: 橙黄色徽章 (.legacy-tag, 保持现有配色)
Step 4.4  改造 user_chat.html @员工面板:
           - 显示员工可用的 MCP 工具徽章 (蓝色)、Skill 徽章 (绿色) 和旧TAG (橙黄色)
Step 4.5  种子数据更新:
           - 8 个默认员工的 skills 迁移到 skill_ids 格式
           - 为每个员工配置合适的 mcp_tool_ids
```

### Phase 5: Crawl4ai MCP 化 (1天)

```
Step 5.1  创建 app/mcp/builtin_tools/crawl4ai_tools.py:
           - collect_with_crawl4ai(url, extract_mode)
           - batch_collect_with_crawl4ai(urls, extract_mode)
Step 5.2  从 deep_collector.py 提取 crawl4ai 调用逻辑为独立函数
Step 5.3  注册到 mcp_tools 表
Step 5.4  废弃 digital_employees.crawl4ai_enabled 字段
Step 5.5  前端移除 crawl4ai 复选框
```

### Phase 6: TAG 重构 (1天)

```
Step 6.1  分析现有旧 TAG 字符串:
           产业专员: ["产业分析", "政策解读", "竞品分析", "趋势预判"]
           天机助手: ["信息检索", "数据分析", "文案撰写", "代码辅助"]
           采集专员: ["数据搜索", "深度采集", "内容提取", "数据整理"]
           文案编写: ["报告撰写", "方案策划", "公文起草", "宣传文案", "演讲稿"]
           新闻聚合: ["新闻检索", "资讯聚合", "热点追踪", "每日简报"]
           科普助手: ["百科问答", "知识科普", "概念解释", "学术参考"]
           随机音乐: ["随机音乐", "歌曲推荐", "音乐点播"]

Step 6.2  迁移策略:
           - 旧 TAG → 在 skills 表中创建对应技能记录 (如果不存在)
           - 旧 skills JSON 数组 → skill_ids JSON 数组
           - 新增 mcp_tool_ids 配置

Step 6.3  前端显示规则:
           .mcp-tag   { background: rgba(94,163,255,0.15); color: #5EA3FF; }   /* 蓝色 */
           .skill-tag { background: rgba(95,184,120,0.15); color: #5FB878; }   /* 绿色 */
           .legacy-tag { background: rgba(255,184,0,0.15); color: #FFB800; }   /* 橙黄色(旧TAG,保持现有风格) */
```

### Phase 7: 集成测试 & 文档 (1天)

```
Step 7.1  编写 test_mcp_refactor.py 测试用例
Step 7.2  端到端测试: 创建员工 → 配置工具 → 前台调用
Step 7.3  更新 docs/design.md
Step 7.4  更新 docs/api.md
Step 7.5  更新 README.md
```

---

## 七、前端 UI 设计要点

### 7.1 MCP 工具管理页面布局

```
┌─────────────────────────────────────────────────────────┐
│  🔧 MCP 工具管理                        [+ 新增工具] [🔄 热重载] │
├─────────────────────────────────────────────────────────┤
│  [全部] [🔍数据仓库] [🔭采集] [🤖员工] [🧠模型] [💬对话] [🎵娱乐] [🕷️爬虫] │
├─────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────┐   │
│  │ ✅ search_warehouse                           🔍 │   │
│  │ 在数据仓库中搜索关键词相关内容                      │   │
│  │ 分类: 数据仓库 | 类型: builtin | 启用                │   │
│  │ [🧪测试] [✏️编辑] [⏸禁用]                           │   │
│  └──────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────┐   │
│  │ ✅ collect_with_crawl4ai                      🕷️ │   │
│  │ 使用Crawl4ai对URL进行智能深度采集                    │   │
│  │ 分类: 爬虫增强 | 类型: builtin | 启用                │   │
│  │ [🧪测试] [✏️编辑] [⏸禁用]                           │   │
│  └──────────────────────────────────────────────────┘   │
│  ...                                                     │
└─────────────────────────────────────────────────────────┘
```

### 7.2 数字员工编辑页 — MCP 工具选择区

```
┌─────────────────────────────────────────────────────────┐
│  选择 MCP 工具                                            │
│  ┌──────────────────────────────────────────────────┐   │
│  │ 🔍 数据仓库                                        │   │
│  │ ☑ search_warehouse   ☑ get_recent_warehouse_data │   │
│  │ ☑ get_warehouse_stats                            │   │
│  │ 🔭 瞭望采集                                        │   │
│  │ ☑ collect_web_data   ☑ deep_collect_url          │   │
│  │ 🕷️ 爬虫增强                                        │   │
│  │ ☐ collect_with_crawl4ai                          │   │
│  │ 🎵 娱乐                                            │   │
│  │ ☐ get_random_music                               │   │
│  └──────────────────────────────────────────────────┘   │
│                                                          │
│  选择 Skill                                              │
│  ┌──────────────────────────────────────────────────┐   │
│  │ ☑ 数据统计 (search_warehouse + prompt)            │   │
│  │ ☑ 新闻摘要 (get_recent_warehouse_data + prompt)   │   │
│  │ ☐ 翻译助手 (纯 prompt)                             │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### 7.3 员工卡片徽章颜色方案

```css
/* MCP 工具徽章 — 蓝色系 */
.mcp-tag {
    background: rgba(94, 163, 255, 0.12);
    color: #5EA3FF;
    border: 1px solid rgba(94, 163, 255, 0.2);
}

/* Skill 徽章 — 绿色系 */
.skill-tag {
    background: rgba(95, 184, 120, 0.12);
    color: #5FB878;
    border: 1px solid rgba(95, 184, 120, 0.2);
}

/* 旧TAG徽章 (兼容过渡期) — 橙黄色系，保持现有风格 */
.legacy-tag {
    background: rgba(255, 184, 0, 0.12);
    color: #FFB800;
    border: 1px solid rgba(255, 184, 0, 0.2);
}
```

---

## 八、种子数据迁移映射

### 8.1 旧 TAG → 新 Skill 映射

| 旧TAG (字符串) | 新 Skill 名称 | 关联 MCP 工具 | 类型 |
|---------------|--------------|--------------|------|
| 信息检索 | 信息检索 | search_warehouse | skill |
| 数据分析 | 数据分析 | get_warehouse_stats | skill |
| 文案撰写 | 文案撰写 | (无, 纯prompt) | skill |
| 代码辅助 | 代码辅助 | (无, 纯prompt) | skill |
| 产业分析 | 产业分析 | get_recent_warehouse_data | skill |
| 政策解读 | 政策解读 | search_warehouse | skill |
| 新闻检索 | 新闻检索 | search_warehouse | skill |
| 深度采集 | 深度采集 | deep_collect_url | skill |
| ... | ... | ... | ... |

### 8.2 员工 MCP 工具配置（推荐）

| 员工 | 推荐 MCP 工具 |
|------|-------------|
| 产业专员 | search_warehouse, get_recent_warehouse_data, get_warehouse_stats, deep_collect_url, collect_with_crawl4ai |
| 天机助手 | search_warehouse, get_recent_warehouse_data, get_warehouse_stats, list_digital_employees, list_conversations |
| 天气 | (API型, 通过 mcp_tool 的 api 类型实现) |
| 采集专员 | collect_web_data, deep_collect_url, collect_with_crawl4ai, search_warehouse |
| 文案编写 | search_warehouse, get_recent_warehouse_data (参考数据用) |
| 新闻聚合 | search_warehouse, get_recent_warehouse_data, collect_web_data |
| 科普助手 | search_warehouse, get_recent_warehouse_data |
| 随机音乐 | get_random_music |

---

## 九、API 路由变更

### 9.1 新增路由

```python
# MCP 工具管理 (main.py 新增)
(r"/admin/mcp/tool",          MCPToolListHandler),
(r"/admin/mcp/tool/add",      MCPToolFormHandler),
(r"/admin/mcp/tool/edit",     MCPToolFormHandler),
(r"/admin/mcp/tool/delete",   MCPToolDeleteHandler),
(r"/admin/mcp/tool/toggle",   MCPToolToggleHandler),
(r"/admin/mcp/tool/test",     MCPToolTestHandler),
(r"/admin/mcp/reload",        MCPToolReloadHandler),

# MCP 工具 API (供前端 AJAX)
(r"/api/mcp/tools",           MCPToolApiHandler),         # GET 工具列表
(r"/api/mcp/tool/([0-9]+)",   MCPToolDetailApiHandler),   # GET 单个工具详情
(r"/api/mcp/tool/test",       MCPToolTestApiHandler),     # POST 执行测试
```

### 9.2 现有路由无需变更

---

## 十、风险与兼容性

### 10.1 向下兼容策略

1. **`digital_employees.skills` 字段**: 保留，继续支持读取旧的 JSON 字符串数组格式。新增 `skill_ids_new` 和 `mcp_tool_ids` 并行使用
2. **`digital_employees.crawl4ai_enabled`**: 保留列但标记废弃。读取时如果 `mcp_tool_ids` 中不包含 crawl4ai 工具但 `crawl4ai_enabled=1`，自动补充
3. **`skills.function_name/function_params`**: 保留列但不再使用。新逻辑通过 `mcp_tool_id` 外键关联
4. **`MCP_TOOL_NAMES` 硬编码列表**: 改为从数据库动态读取
5. **`register_all_tools()`**: 保留兼容，内部改为从数据库加载 + 代码定义合并

### 10.2 回滚方案

如果重构出现问题，可通过以下步骤回滚：
1. 数据库迁移脚本设计为可逆 (提供 down 迁移)
2. 前端新旧 TAG 显示逻辑可独立切换
3. MCP Server 支持双模式: 数据库驱动 / 代码定义 (fallback)

### 10.3 性能考量

- MCP 工具从数据库加载后缓存在 MCPServer 内存中
- 热重载通过管理后台手动触发，不影响正常请求
- 工具权限过滤在 MCPClient 层完成，不增加数据库查询

---

## 十一、时间估算

| 阶段 | 内容 | 预计工时 |
|------|------|---------|
| Phase 1 | 数据层改造 | 1-2 天 |
| Phase 2 | MCP 核心重构 | 2-3 天 |
| Phase 3 | MCP 管理后台 | 2 天 |
| Phase 4 | 数字员工改造 | 1-2 天 |
| Phase 5 | Crawl4ai MCP 化 | 1 天 |
| Phase 6 | TAG 重构 | 1 天 |
| Phase 7 | 测试 & 文档 | 1 天 |
| **总计** | | **9-12 天** |

---

## 十二、总结

本次重构的核心思想是 **「一切皆 MCP Tool」**，通过以下关键变更实现：

1. **工具注册数据库化** — 从硬编码 10 个工具 → 数据库驱动的 20+ 工具注册中心
2. **MCP 管理可视化** — 新增管理页面，支持启用/禁用/配置/测试
3. **员工能力工具化** — 数字员工的能力由 MCP 工具集 + Skill 集定义，而非模糊的 TAG
4. **Crawl4ai 标准化** — 从硬编码复选框 → 标准 MCP 工具
5. **TAG 视觉重构** — MCP 工具(蓝) · Skill(绿) · 旧TAG(橙黄) 三色徽章体系
6. **完全向下兼容** — 旧数据自动迁移，旧格式继续可用
