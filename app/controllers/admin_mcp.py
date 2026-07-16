"""
admin_mcp.py — MCP 工具管理控制器 (v0.10 新增)

管理员管理 MCP 工具注册表:
- 工具列表（分页/分类筛选/状态筛选）
- 工具配置编辑（名称/描述/Schema/启用）
- 工具在线测试
- 工具启用/禁用
- 热重载
"""

import json
import logging
import time

import tornado.web

from app.controllers.admin_base import AdminBaseHandler
from app.models.mcp_tool import MCPToolRepository, MCP_TOOL_CATEGORIES, TOOL_TYPES
from app.utils.security import write_audit_log

logger = logging.getLogger(__name__)


class MCPToolListHandler(AdminBaseHandler):
    """MCP 工具列表页"""

    @tornado.web.authenticated
    def get(self):
        try:
            page = max(1, int(self.get_query_argument("page", 1)))
        except (ValueError, TypeError):
            page = 1
        category = self.get_query_argument("category", "").strip()
        tool_type = self.get_query_argument("tool_type", "").strip()
        is_enabled_str = self.get_query_argument("enabled", "").strip()
        is_enabled = None
        if is_enabled_str == "1":
            is_enabled = 1
        elif is_enabled_str == "0":
            is_enabled = 0

        rows, total = MCPToolRepository.get_all(
            page=page, page_size=20, category=category,
            tool_type=tool_type, is_enabled=is_enabled,
        )
        total_pages = max(1, (total + 20 - 1) // 20)
        categories = MCPToolRepository.get_categories()

        # 获取注册中心的加载状态
        loaded_names = []
        try:
            from app.mcp.registry import MCPToolRegistry
            registry = MCPToolRegistry.get_instance()
            loaded_names = registry.loaded_tool_names
        except Exception:
            pass

        self.render(
            "admin/mcp_tool_list.html",
            title="MCP 工具管理 — 瞭望与问数系统",
            username=self.current_user,
            tools=rows,
            page=page,
            total=total,
            total_pages=total_pages,
            category=category,
            tool_type=tool_type,
            is_enabled=is_enabled_str,
            categories=categories,
            all_categories=MCP_TOOL_CATEGORIES,
            tool_types=TOOL_TYPES,
            loaded_names=loaded_names,
        )


class MCPToolFormHandler(AdminBaseHandler):
    """MCP 工具配置编辑页"""

    @tornado.web.authenticated
    def get(self):
        tool_id = self.get_query_argument("id", None)
        tool = None
        if tool_id:
            try:
                tool = MCPToolRepository.get_by_id(int(tool_id))
            except (ValueError, TypeError):
                self.write('<script>alert("无效的工具ID");window.history.back();</script>')
                return
            if not tool:
                self.write('<script>alert("工具不存在");window.history.back();</script>')
                return

        self.render(
            "admin/mcp_tool_form.html",
            title="编辑 MCP 工具" if tool else "新增 MCP 工具",
            username=self.current_user,
            tool=tool,
            data_sources=tool.get("data_sources", "[]") if tool else "[]",
            transform_script=tool.get("transform_script", "") if tool else "",
            script_enabled=tool.get("script_enabled", "0") if tool else "0",
            categories=MCP_TOOL_CATEGORIES,
            tool_types=TOOL_TYPES,
        )

    @tornado.web.authenticated
    def post(self):
        tool_id = self.get_body_argument("id", None)
        name = self.get_body_argument("name", "").strip()
        display_name = self.get_body_argument("display_name", "").strip()
        description = self.get_body_argument("description", "").strip()
        category = self.get_body_argument("category", "general").strip()
        tool_type = self.get_body_argument("tool_type", "script").strip()
        input_schema = self.get_body_argument("input_schema", "{}").strip()
        output_schema = self.get_body_argument("output_schema", "{}").strip()
        try:
            is_enabled = int(self.get_body_argument("is_enabled", "1"))
        except (ValueError, TypeError):
            is_enabled = 1
        try:
            sort_order = int(self.get_body_argument("sort_order", "0"))
        except (ValueError, TypeError):
            sort_order = 0
        data_sources = self.get_body_argument("data_sources", "[]")
        transform_script = self.get_body_argument("transform_script", "")
        script_enabled = 1 if self.get_body_argument("script_enabled", "0") == "1" else 0

        if not name or not display_name:
            self.write('<script>alert("工具名称和显示名称不能为空");window.history.back();</script>')
            return

        # 校验 JSON 格式
        for field_name, field_val in [("input_schema", input_schema), ("output_schema", output_schema)]:
            try:
                json.loads(field_val)
            except (json.JSONDecodeError, TypeError):
                self.write(f'<script>alert("{field_name} JSON 格式无效");window.history.back();</script>')
                return

        # 校验 data_sources JSON 格式
        try:
            json.loads(data_sources)
        except (json.JSONDecodeError, TypeError):
            self.write('<script>alert("数据源格式错误：必须是有效的 JSON 数组");window.history.back();</script>')
            return

        if tool_id:
            try:
                tool_id_int = int(tool_id)
            except (ValueError, TypeError):
                self.write('<script>alert("无效的工具ID");window.history.back();</script>')
                return
            success = MCPToolRepository.update(
                tool_id_int, name=name, display_name=display_name,
                description=description, category=category, tool_type=tool_type,
                input_schema=input_schema, output_schema=output_schema,
                is_enabled=is_enabled, sort_order=sort_order,
                data_sources=data_sources, transform_script=transform_script,
                script_enabled=script_enabled,
            )
            if success:
                write_audit_log("MCP_TOOL_UPDATE", self.current_user,
                                f"tool:{name}", f"更新 MCP 工具配置", self.request.remote_ip or "")
                self.write('<script>alert("工具更新成功");location.href="/admin/mcp/tool";</script>')
            else:
                self.write('<script>alert("更新失败，可能名称重复");window.history.back();</script>')
        else:
            new_id = MCPToolRepository.create(
                name=name, display_name=display_name, description=description,
                category=category, tool_type=tool_type,
                input_schema=input_schema, output_schema=output_schema,
                is_enabled=is_enabled, sort_order=sort_order,
                data_sources=data_sources, transform_script=transform_script,
                script_enabled=script_enabled,
            )
            if new_id > 0:
                write_audit_log("MCP_TOOL_CREATE", self.current_user,
                                f"tool:{name}", f"创建 MCP 工具 ID={new_id}", self.request.remote_ip or "")
                self.write('<script>alert("工具创建成功");location.href="/admin/mcp/tool";</script>')
            else:
                self.write('<script>alert("创建失败，可能名称重复");window.history.back();</script>')


class MCPToolDeleteHandler(AdminBaseHandler):
    """MCP 工具删除"""

    @tornado.web.authenticated
    def post(self):
        tool_id = self.get_body_argument("id", None)
        if not tool_id:
            self.write({"code": 1, "msg": "缺少工具ID"})
            return
        try:
            tool_id = int(tool_id)
        except (ValueError, TypeError):
            self.write({"code": 1, "msg": "无效的工具ID"})
            return

        success = MCPToolRepository.delete(tool_id)
        if success:
            write_audit_log("MCP_TOOL_DELETE", self.current_user,
                            f"tool_id:{tool_id}", "删除 MCP 工具", self.request.remote_ip or "")
            self.write({"code": 0, "msg": "删除成功"})
        else:
            self.write({"code": 1, "msg": "删除失败，系统工具不可删除"})


class MCPToolToggleHandler(AdminBaseHandler):
    """MCP 工具启用/禁用"""

    @tornado.web.authenticated
    def post(self):
        tool_id = self.get_body_argument("id", None)
        if not tool_id:
            self.write({"code": 1, "msg": "缺少工具ID"})
            return
        try:
            tool_id = int(tool_id)
        except (ValueError, TypeError):
            self.write({"code": 1, "msg": "无效的工具ID"})
            return

        new_status = MCPToolRepository.toggle_enabled(tool_id)
        if new_status >= 0:
            write_audit_log("MCP_TOOL_TOGGLE", self.current_user,
                            f"tool_id:{tool_id}", f"切换状态 -> {new_status}", self.request.remote_ip or "")
            self.write({"code": 0, "msg": "切换成功", "is_enabled": new_status})
        else:
            self.write({"code": 1, "msg": "工具不存在"})


class MCPToolTestHandler(AdminBaseHandler):
    """MCP 工具在线测试（API）"""

    @tornado.web.authenticated
    async def post(self):
        tool_id = self.get_body_argument("id", None)
        test_params_str = self.get_body_argument("params", "{}").strip()

        if not tool_id:
            self.write({"code": 1, "msg": "缺少工具ID"})
            return
        try:
            tool_id = int(tool_id)
        except (ValueError, TypeError):
            self.write({"code": 1, "msg": "无效的工具ID"})
            return

        try:
            test_params = json.loads(test_params_str)
        except json.JSONDecodeError:
            self.write({"code": 1, "msg": "参数 JSON 格式无效"})
            return

        tool_row = MCPToolRepository.get_by_id(tool_id)
        if not tool_row:
            self.write({"code": 1, "msg": "工具不存在"})
            return

        # 通过 registry 构建工具并执行
        from app.mcp.registry import _build_tool_from_db_row
        tool = _build_tool_from_db_row(tool_row)
        if not tool:
            self.write({"code": 1, "msg": "工具构建失败，请检查工具配置"})
            return

        start_time = time.time()
        try:
            result = await tool.call(test_params)
            duration_ms = int((time.time() - start_time) * 1000)
            result_str = json.dumps(result, ensure_ascii=False, indent=2)
            MCPToolRepository.log_test(
                tool_id, test_params_str, result_str, 1, duration_ms
            )
            self.write({
                "code": 0,
                "msg": "执行成功",
                "result": result,
                "duration_ms": duration_ms,
            })
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            error_str = str(e)
            MCPToolRepository.log_test(
                tool_id, test_params_str, error_str, 0, duration_ms
            )
            self.write({
                "code": 1,
                "msg": f"执行失败: {error_str}",
                "duration_ms": duration_ms,
            })


class MCPToolReloadHandler(AdminBaseHandler):
    """MCP 工具热重载"""

    @tornado.web.authenticated
    def post(self):
        try:
            from app.mcp.registry import MCPToolRegistry
            registry = MCPToolRegistry.get_instance()
            count = registry.reload_all()
            write_audit_log("MCP_TOOL_RELOAD", self.current_user,
                            "", f"热重载完成: {count} 个工具", self.request.remote_ip or "")
            self.write({"code": 0, "msg": f"热重载成功，已加载 {count} 个工具", "count": count})
        except Exception as e:
            self.write({"code": 1, "msg": f"热重载失败: {str(e)}"})


class MCPToolTestLogsHandler(AdminBaseHandler):
    """获取工具测试日志"""

    @tornado.web.authenticated
    def get(self):
        tool_id = self.get_query_argument("id", None)
        if not tool_id:
            self.write({"code": 1, "msg": "缺少工具ID"})
            return
        try:
            tool_id = int(tool_id)
        except (ValueError, TypeError):
            self.write({"code": 1, "msg": "无效的工具ID"})
            return

        logs = MCPToolRepository.get_test_logs(tool_id, limit=20)
        self.write({"code": 0, "data": logs})
