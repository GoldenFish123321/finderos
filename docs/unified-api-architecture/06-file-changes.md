# 文件变更清单

> 主文档：[README.md](./README.md) — 架构总览

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
└── unified-api-architecture/       # 本文档目录
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

> 相关文档：[数据库变更方案](./01-database-schema.md) | [迁移计划](./08-migration-plan.md)
