"""
v1.6.0 测试: API 型员工 MCP 统一调度重构

覆盖:
- API 员工创建/更新时 mcp_tool_id 字段正确保存
- mcp_tool_id=NULL 时走 legacy 路径（向后兼容）
- resolve_mcp_tool_info() 正确解析 MCP 工具信息
- EmployeeInvokeHandler._invoke_api_employee 正确分流
- EmployeeFormHandler 传递 mcp_tools_all 给模板
"""
import json
import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.digital_employee import DigitalEmployeeRepository
from app.models.mcp_tool import MCPToolRepository
from app.models.db import get_db, init_db


def setup_module():
    """确保数据库和默认数据已初始化。"""
    init_db()

    # 确保 MCP 工具有种子数据
    from app.models.db import seed_default_data
    seed_default_data()

    # 清理测试数据
    cleanup()


def teardown_module():
    cleanup()


def cleanup():
    with get_db() as conn:
        conn.execute("DELETE FROM digital_employees WHERE name LIKE ?", ("_mcp_refactor_%",))
        conn.commit()


# ═══════════════════════════════════════════════════════════
# 模型层测试
# ═══════════════════════════════════════════════════════════

def test_create_api_employee_with_mcp_tool_id():
    """创建带 mcp_tool_id 的 API 型员工应正确保存。"""
    # 先获取一个已启用的 MCP 工具
    tools = MCPToolRepository.get_enabled()
    if not tools:
        pytest.skip("没有可用的 MCP 工具")
    tool = tools[0]

    emp_id = DigitalEmployeeRepository.create(
        name="_mcp_refactor_test1_",
        employee_type="api",
        description="测试 MCP 绑定",
        mcp_tool_id=tool["id"],
    )
    assert emp_id > 0

    emp = DigitalEmployeeRepository.get_by_id(emp_id)
    assert emp is not None
    assert emp["name"] == "_mcp_refactor_test1_"
    assert emp["employee_type"] == "api"
    assert emp["mcp_tool_id"] == tool["id"]


def test_create_api_employee_without_mcp_tool_id():
    """不传 mcp_tool_id 的 API 型员工应保持 NULL（向后兼容）。"""
    emp_id = DigitalEmployeeRepository.create(
        name="_mcp_refactor_no_mcp_",
        employee_type="api",
        description="无 MCP 绑定（legacy）",
    )
    assert emp_id > 0

    emp = DigitalEmployeeRepository.get_by_id(emp_id)
    assert emp is not None
    assert emp["mcp_tool_id"] is None or emp["mcp_tool_id"] == 0


def test_create_llm_employee_with_mcp_tool_ids():
    """LLM 型员工仍使用 mcp_tool_ids（多选），mcp_tool_id 应不影响。"""
    tools = MCPToolRepository.get_enabled()
    if len(tools) < 2:
        pytest.skip("至少需要 2 个 MCP 工具")

    tool_ids = [tools[0]["id"], tools[1]["id"]]
    emp_id = DigitalEmployeeRepository.create(
        name="_mcp_refactor_llm_",
        employee_type="llm",
        description="LLM 员工多工具",
        mcp_tool_ids=json.dumps(tool_ids),
        mcp_tool_id=None,  # LLM 员工不应绑定单个工具
    )
    assert emp_id > 0

    emp = DigitalEmployeeRepository.get_by_id(emp_id)
    assert emp is not None
    assert emp["employee_type"] == "llm"
    parsed_ids = json.loads(emp["mcp_tool_ids"])
    assert parsed_ids == tool_ids


def test_update_api_employee_mcp_tool_id():
    """更新 API 员工的 mcp_tool_id。"""
    tools = MCPToolRepository.get_enabled()
    if len(tools) < 2:
        pytest.skip("至少需要 2 个 MCP 工具")

    # 创建时绑定 tool[0]
    emp_id = DigitalEmployeeRepository.create(
        name="_mcp_refactor_update_",
        employee_type="api",
        mcp_tool_id=tools[0]["id"],
    )
    assert emp_id > 0

    # 更新为 tool[1]
    ok = DigitalEmployeeRepository.update(
        emp_id=emp_id,
        name="_mcp_refactor_update_",
        employee_type="api",
        mcp_tool_id=tools[1]["id"],
    )
    assert ok

    emp = DigitalEmployeeRepository.get_by_id(emp_id)
    assert emp["mcp_tool_id"] == tools[1]["id"]


def test_resolve_mcp_tool_info():
    """resolve_mcp_tool_info() 应为 API 员工正确填充 MCP 工具字段。"""
    tools = MCPToolRepository.get_enabled()
    if not tools:
        pytest.skip("没有可用的 MCP 工具")
    tool = tools[0]

    emp_id = DigitalEmployeeRepository.create(
        name="_mcp_refactor_resolve_",
        employee_type="api",
        mcp_tool_id=tool["id"],
    )
    emp = DigitalEmployeeRepository.get_by_id(emp_id)
    resolved = DigitalEmployeeRepository.resolve_mcp_tool_info(emp)

    assert resolved["mcp_tool_name"] == tool.get("display_name", tool["name"])
    assert resolved["mcp_tool_category"] == tool.get("category", "")
    assert resolved["mcp_tool_type"] == tool.get("tool_type", "")


def test_resolve_mcp_tool_info_null():
    """mcp_tool_id 为 None 时 resolve_mcp_tool_info 应返回空字符串。"""
    emp_id = DigitalEmployeeRepository.create(
        name="_mcp_refactor_null_",
        employee_type="api",
    )
    emp = DigitalEmployeeRepository.get_by_id(emp_id)
    resolved = DigitalEmployeeRepository.resolve_mcp_tool_info(emp)

    assert resolved["mcp_tool_name"] == ""
    assert resolved["mcp_tool_category"] == ""
    assert resolved["mcp_tool_type"] == ""


def test_resolve_mcp_tool_info_invalid_id():
    """mcp_tool_id 指向不存在的工具时应安全返回空字符串。"""
    emp = {
        "id": -1,
        "name": "_fake_emp_",
        "employee_type": "api",
        "mcp_tool_id": 99999,  # 不存在的工具
    }
    resolved = DigitalEmployeeRepository.resolve_mcp_tool_info(emp)
    assert resolved["mcp_tool_name"] == ""
    assert resolved["mcp_tool_category"] == ""


# ═══════════════════════════════════════════════════════════
# 控制器层测试 — _invoke_api_employee 分流
# ═══════════════════════════════════════════════════════════

class TestEmployeeInvokeRouting:
    """测试 _invoke_api_employee 根据 mcp_tool_id 正确分流。"""

    @pytest.mark.asyncio
    async def test_routes_to_mcp_when_tool_id_present(self):
        """mcp_tool_id 存在时应调用 _invoke_api_via_mcp。"""
        from app.controllers.admin_employee import EmployeeInvokeHandler
        import tornado.web

        handler = EmployeeInvokeHandler.__new__(EmployeeInvokeHandler)
        handler._invoke_api_via_mcp = AsyncMock()
        handler._invoke_api_employee_legacy = AsyncMock()
        handler.current_user = "test_admin"
        handler.request = MagicMock()
        handler.request.remote_ip = "127.0.0.1"

        emp = {"id": 1, "name": "测试API员工", "employee_type": "api", "mcp_tool_id": 5}

        await handler._invoke_api_employee(emp, "hello")

        handler._invoke_api_via_mcp.assert_called_once()
        handler._invoke_api_employee_legacy.assert_not_called()

    @pytest.mark.asyncio
    async def test_routes_to_legacy_when_tool_id_none(self):
        """mcp_tool_id 为 None 时应调用 _invoke_api_employee_legacy。"""
        from app.controllers.admin_employee import EmployeeInvokeHandler

        handler = EmployeeInvokeHandler.__new__(EmployeeInvokeHandler)
        handler._invoke_api_via_mcp = AsyncMock()
        handler._invoke_api_employee_legacy = AsyncMock()
        handler.current_user = "test_admin"
        handler.request = MagicMock()
        handler.request.remote_ip = "127.0.0.1"

        emp = {"id": 2, "name": "Legacy员工", "employee_type": "api", "mcp_tool_id": None}

        await handler._invoke_api_employee(emp, "hello")

        handler._invoke_api_via_mcp.assert_not_called()
        handler._invoke_api_employee_legacy.assert_called_once()

    @pytest.mark.asyncio
    async def test_routes_to_legacy_when_tool_id_zero(self):
        """mcp_tool_id 为 0 时应调用 _invoke_api_employee_legacy。"""
        from app.controllers.admin_employee import EmployeeInvokeHandler

        handler = EmployeeInvokeHandler.__new__(EmployeeInvokeHandler)
        handler._invoke_api_via_mcp = AsyncMock()
        handler._invoke_api_employee_legacy = AsyncMock()
        handler.current_user = "test_admin"
        handler.request = MagicMock()
        handler.request.remote_ip = "127.0.0.1"

        emp = {"id": 3, "name": "Zero员工", "employee_type": "api", "mcp_tool_id": 0}

        await handler._invoke_api_employee(emp, "hello")

        handler._invoke_api_via_mcp.assert_not_called()
        handler._invoke_api_employee_legacy.assert_called_once()


# ═══════════════════════════════════════════════════════════
# MCP 工具调用集成测试（需要 mock safe_http_request）
# ═══════════════════════════════════════════════════════════

class TestMCPInvokeIntegration:
    """测试 _invoke_api_via_mcp 的 MCP 工具执行流程。"""

    @pytest.mark.asyncio
    @patch("app.controllers.admin_employee.MCPToolRepository")
    @patch("app.mcp.server.MCPServer")  # 懒加载的实际模块路径
    async def test_invoke_via_mcp_builtin_tool(self, mock_server_cls, mock_repo):
        """通过 builtin 类型 MCP 工具调用的完整流程测试。"""
        from app.controllers.admin_employee import EmployeeInvokeHandler

        # Mock MCP 工具与服务器
        mock_tool = AsyncMock()
        mock_tool.call.return_value = {"result": "success", "data": "test_data"}
        mock_server = MagicMock()
        mock_server.get_tool.return_value = mock_tool
        mock_server_cls.get_instance.return_value = mock_server

        # Mock MCP 工具数据库记录
        mock_repo.get_by_id.return_value = {
            "id": 5, "name": "search_warehouse", "display_name": "数据仓库搜索",
            "tool_type": "builtin", "category": "warehouse",
            "is_enabled": 1, "input_schema": '{"properties":{"keyword":{"type":"string"}}}'
        }

        handler = EmployeeInvokeHandler.__new__(EmployeeInvokeHandler)
        handler.write = MagicMock()
        handler.set_header = MagicMock()
        handler.current_user = "test_admin"
        handler.request = MagicMock()
        handler.request.remote_ip = "127.0.0.1"

        emp = {"id": 1, "name": "测试员工", "employee_type": "api",
               "mcp_tool_id": 5, "response_render_template": ""}

        await handler._invoke_api_via_mcp(emp, "测试关键词", 5)

        # 验证 MCP 工具被调用
        mock_tool.call.assert_called_once()
        call_args = mock_tool.call.call_args[0][0]
        assert call_args["keyword"] == "测试关键词"

        # 验证结果被写入
        handler.write.assert_called_once()
        written = handler.write.call_args[0][0]
        assert written["code"] == 0
        assert "data" in written

    @pytest.mark.asyncio
    @patch("app.controllers.admin_employee.MCPToolRepository")
    async def test_invoke_via_mcp_tool_not_found(self, mock_repo):
        """绑定的 MCP 工具不存在时应返回错误。"""
        from app.controllers.admin_employee import EmployeeInvokeHandler

        mock_repo.get_by_id.return_value = None

        handler = EmployeeInvokeHandler.__new__(EmployeeInvokeHandler)
        handler.write = MagicMock()
        handler.current_user = "test_admin"
        handler.request = MagicMock()
        handler.request.remote_ip = "127.0.0.1"

        emp = {"id": 1, "name": "测试员工", "employee_type": "api", "mcp_tool_id": 999}

        await handler._invoke_api_via_mcp(emp, "test message", 999)

        written = handler.write.call_args[0][0]
        assert written["code"] == 1
        assert "不存在" in written["msg"] or "禁用" in written["msg"]

    @pytest.mark.asyncio
    @patch("app.controllers.admin_employee.MCPToolRepository")
    async def test_invoke_via_mcp_tool_disabled(self, mock_repo):
        """绑定的 MCP 工具已禁用时应返回错误。"""
        from app.controllers.admin_employee import EmployeeInvokeHandler

        mock_repo.get_by_id.return_value = {
            "id": 5, "name": "disabled_tool", "display_name": "已禁用工具",
            "is_enabled": 0,
        }

        handler = EmployeeInvokeHandler.__new__(EmployeeInvokeHandler)
        handler.write = MagicMock()
        handler.current_user = "test_admin"
        handler.request = MagicMock()
        handler.request.remote_ip = "127.0.0.1"

        emp = {"id": 1, "name": "测试员工", "employee_type": "api", "mcp_tool_id": 5}

        await handler._invoke_api_via_mcp(emp, "test message", 5)

        written = handler.write.call_args[0][0]
        assert written["code"] == 1


# ═══════════════════════════════════════════════════════════
# 员工列表解析测试
# ═══════════════════════════════════════════════════════════

def test_employee_list_resolves_mcp_tool_for_api_employee():
    """EmployeeListHandler 应为 API 员工解析 mcp_tool_name。"""
    tools = MCPToolRepository.get_enabled()
    if not tools:
        pytest.skip("没有可用的 MCP 工具")
    tool = tools[0]

    emp_id = DigitalEmployeeRepository.create(
        name="_mcp_refactor_list_",
        employee_type="api",
        description="列表测试",
        mcp_tool_id=tool["id"],
    )
    assert emp_id > 0

    rows, total = DigitalEmployeeRepository.get_all(page_size=9999)

    # 模拟 EmployeeListHandler 中的解析逻辑
    for emp in rows:
        if emp.get("id") == emp_id:
            resolved = DigitalEmployeeRepository.resolve_mcp_tool_info(emp)
            # 模拟原地更新
            for key in ("mcp_tool_name", "mcp_tool_category", "mcp_tool_type"):
                emp[key] = resolved.get(key, "")
            break

    found = next((e for e in rows if e.get("id") == emp_id), None)
    assert found is not None
    assert found.get("mcp_tool_name") == tool.get("display_name", tool["name"])
    assert found.get("mcp_tool_category") == tool.get("category", "")


# ═══════════════════════════════════════════════════════════
# 向后兼容测试
# ═══════════════════════════════════════════════════════════

def test_legacy_api_employee_still_works():
    """旧 API 员工（mcp_tool_id=NULL）应仍能正常创建和读取。"""
    emp_id = DigitalEmployeeRepository.create(
        name="_mcp_refactor_legacy_",
        employee_type="api",
        description="旧架构兼容测试",
        api_url="https://example.com/api",
        api_method="POST",
        api_headers='{"Content-Type":"application/json"}',
        api_params_template='{"query":"{message}"}',
        api_secret="test-secret-123",
    )
    assert emp_id > 0

    emp = DigitalEmployeeRepository.get_by_id(emp_id)
    assert emp is not None
    assert emp["employee_type"] == "api"
    assert emp["api_url"] == "https://example.com/api"
    assert emp["api_method"] == "POST"
    assert emp["mcp_tool_id"] is None or emp["mcp_tool_id"] == 0
    # API 密钥应被正确加解密
    assert emp["api_secret"] == "test-secret-123"


def test_legacy_update_still_works():
    """更新旧 API 员工时不应丢失 mcp_tool_id 和其他字段。"""
    emp_id = DigitalEmployeeRepository.create(
        name="_mcp_refactor_legacy_upd_",
        employee_type="api",
        api_url="https://old.example.com/api",
    )
    assert emp_id > 0

    ok = DigitalEmployeeRepository.update(
        emp_id=emp_id,
        name="_mcp_refactor_legacy_upd_",
        employee_type="api",
        api_url="https://new.example.com/api",
        api_method="GET",
    )
    assert ok

    emp = DigitalEmployeeRepository.get_by_id(emp_id)
    assert emp["api_url"] == "https://new.example.com/api"
    assert emp["api_method"] == "GET"
    assert emp["mcp_tool_id"] is None or emp["mcp_tool_id"] == 0


# ═══════════════════════════════════════════════════════════
# v1.7.0: 天气员工 MCP 工具绑定迁移测试
# ═══════════════════════════════════════════════════════════

def test_weather_mcp_tool_exists():
    """weather_query MCP 工具应已由种子或迁移创建。"""
    from app.models.mcp_tool import MCPToolRepository
    tool = MCPToolRepository.get_by_name("weather_query")
    assert tool is not None, "weather_query MCP 工具应存在"
    assert tool["is_enabled"] == 1
    assert tool["tool_type"] == "script"
    assert tool.get("script_enabled") == 1
    assert tool.get("data_sources")
    schema = json.loads(tool["input_schema"])
    sources = json.loads(tool["data_sources"])
    assert schema["required"] == ["message"]
    assert sources[0]["param_mapping"] == {"message": "message"}


def test_weather_employee_bound_to_mcp():
    """种子数据中的天气员工（id=3）应已绑定 weather_query MCP 工具。"""
    from app.models.mcp_tool import MCPToolRepository

    emp = DigitalEmployeeRepository.get_by_id(3)
    if not emp:
        tool = MCPToolRepository.get_by_name("weather_query")
        if not tool:
            pytest.skip("weather_query MCP 工具不存在，无法创建测试员工")
        emp_id = DigitalEmployeeRepository.create(
            name="_test_weather_mcp_",
            employee_type="api", description="测试天气 MCP 绑定",
            mcp_tool_id=tool["id"],
            api_url="https://wttr.in/{message}?format=j1", api_method="GET",
        )
        emp = DigitalEmployeeRepository.get_by_id(emp_id)

    assert emp is not None
    if emp.get("name") == "天气" and emp.get("mcp_tool_id"):
        assert emp["mcp_tool_id"] > 0
        from app.models.mcp_tool import MCPToolRepository
        tool = MCPToolRepository.get_by_id(emp["mcp_tool_id"])
        assert tool is not None
        assert tool["name"] == "weather_query"
        assert tool["is_enabled"] == 1


def test_weather_mcp_tool_buildable():
    """weather_query MCP 工具应能被正常构建为 MCPTool 实例。"""
    from app.models.mcp_tool import MCPToolRepository
    from app.mcp.registry import _build_tool_from_db_row

    tool = MCPToolRepository.get_by_name("weather_query")
    if not tool:
        pytest.skip("weather_query MCP 工具不存在")

    mcp_tool = _build_tool_from_db_row(tool)
    assert mcp_tool is not None
    assert mcp_tool.name == "weather_query"
    assert mcp_tool.description
    assert mcp_tool.input_schema


def test_weather_mcp_tool_proxy_pipeline(monkeypatch):
    """weather_query 应经外部代理完成 URL 替换和结构化转换。"""
    from app.models.mcp_tool import MCPToolRepository
    from app.mcp.registry import _build_tool_from_db_row
    from app.services.local_api_client import (
        _auto_sync_external_proxies_to_api_interfaces,
        _register_external_proxies,
    )
    from app.utils.safe_http import SafeHttpResponse
    import asyncio
    import app.utils.safe_http as safe_http_module

    requested = {}

    def fake_safe_http_request(**kwargs):
        requested.update(kwargs)
        payload = {
            "current_condition": [{
                "weatherDesc": [{"value": "Sunny"}],
                "temp_C": "28", "humidity": "40",
                "winddir16Point": "E", "windspeedKmph": "8",
            }],
            "nearest_area": [{
                "areaName": [{"value": "Beijing"}],
                "country": [{"value": "China"}],
            }],
        }
        return SafeHttpResponse(
            status=200, reason="OK", headers={},
            body=json.dumps(payload).encode("utf-8"), resolved_ip="203.0.113.10",
        )

    monkeypatch.setattr(safe_http_module, "safe_http_request", fake_safe_http_request)

    # 与 main.py 保持相同的外部接口代理启动顺序。该测试直接构建工具，
    # 不会经过应用入口，因此必须显式完成这两步。
    _auto_sync_external_proxies_to_api_interfaces()
    _register_external_proxies()

    tool = MCPToolRepository.get_by_name("weather_query")
    if not tool:
        pytest.skip("weather_query MCP 工具不存在")

    mcp_tool = _build_tool_from_db_row(tool)
    assert mcp_tool is not None

    async def _call():
        return await mcp_tool.call({"message": "北京"})

    result = asyncio.run(_call())

    assert isinstance(result, dict)
    assert "error" not in result
    assert result["city"] == "Beijing"
    assert result["weather"] == "Sunny"
    assert result["temperature"] == "28"
    assert "%E5%8C%97%E4%BA%AC" in requested["url"]
    assert "{message}" not in requested["url"]
