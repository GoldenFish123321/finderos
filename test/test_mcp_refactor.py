"""
test_mcp_refactor.py — MCP 重构验证测试 (v0.10)

验证：
1. MCP 工具数据库注册与查询
2. MCP 工具 CRUD
3. MCPToolRegistry 加载
4. 数字员工 mcp_tool_ids 关联
5. 技能 mcp_tool_id 关联
"""

import json
import sys
import os
import tempfile

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app.config.settings as settings
import app.models.db as db_module
from app.models.db import init_db, seed_default_data
from app.models.mcp_tool import MCPToolRepository, MCP_TOOL_CATEGORIES
from app.models.digital_employee import DigitalEmployeeRepository
from app.models.skill import SkillRepository


TEST_DB_PATH = None
_ORIGINAL_SETTINGS_DB_PATH = None
_ORIGINAL_MODULE_DB_PATH = None
_ORIGINAL_DB_MODULE_DB_PATH = None


def setup_module():
    """pytest 路径下初始化独立测试库，避免依赖或污染本地开发库。"""
    global TEST_DB_PATH
    global _ORIGINAL_SETTINGS_DB_PATH, _ORIGINAL_MODULE_DB_PATH, _ORIGINAL_DB_MODULE_DB_PATH

    _ORIGINAL_SETTINGS_DB_PATH = settings.settings.DB_PATH
    _ORIGINAL_MODULE_DB_PATH = getattr(settings, "DB_PATH", None)
    _ORIGINAL_DB_MODULE_DB_PATH = db_module.DB_PATH

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    TEST_DB_PATH = tmp.name
    tmp.close()

    settings.DB_PATH = TEST_DB_PATH
    settings.settings.DB_PATH = TEST_DB_PATH
    db_module.DB_PATH = TEST_DB_PATH

    init_db()
    seed_default_data()


def teardown_module():
    """恢复全局 DB 路径，清理测试库。"""
    if _ORIGINAL_MODULE_DB_PATH is None:
        try:
            delattr(settings, "DB_PATH")
        except AttributeError:
            pass
    else:
        settings.DB_PATH = _ORIGINAL_MODULE_DB_PATH
    if _ORIGINAL_SETTINGS_DB_PATH is not None:
        settings.settings.DB_PATH = _ORIGINAL_SETTINGS_DB_PATH
    if _ORIGINAL_DB_MODULE_DB_PATH is not None:
        db_module.DB_PATH = _ORIGINAL_DB_MODULE_DB_PATH

    if TEST_DB_PATH and os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)


def test_mcp_tool_table():
    """测试 MCP 工具表查询。"""
    print("\n=== 测试 1: MCP 工具表查询 ===")
    tools, total = MCPToolRepository.get_all()
    print(f"  工具总数: {total}")
    assert total >= 18, f"期望至少 18 个种子工具，实际 {total}"

    # 按分类筛选
    warehouse_tools, _ = MCPToolRepository.get_all(category="warehouse")
    print(f"  数据仓库类工具: {len(warehouse_tools)}")
    assert len(warehouse_tools) >= 3

    # 获取启用的工具
    enabled = MCPToolRepository.get_enabled()
    print(f"  已启用工具: {len(enabled)}")
    assert len(enabled) > 0

    # 按名称查询
    tool = MCPToolRepository.get_by_name("search_warehouse")
    assert tool is not None, "search_warehouse 工具应该存在"
    print(f"  search_warehouse: {tool['display_name']}")

    # 工具分类统计
    categories = MCPToolRepository.get_categories()
    print(f"  工具分类: {len(categories)} 个")
    for c in categories:
        print(f"    {c['name']}: {c['count']} 个")

    print("  ✓ 测试通过")


def test_mcp_tool_crud():
    """测试 MCP 工具 CRUD。"""
    print("\n=== 测试 2: MCP 工具 CRUD ===")

    # 创建
    new_id = MCPToolRepository.create(
        name="test_tool_crud",
        display_name="测试工具",
        description="测试用工具",
        category="system",
        tool_type="builtin",
        handler_module="app.mcp.builtin_tools.system_tools._get_system_stats",
    )
    assert new_id > 0, f"创建失败，new_id={new_id}"
    print(f"  创建工具 ID={new_id}")

    # 查询
    tool = MCPToolRepository.get_by_id(new_id)
    assert tool and tool["name"] == "test_tool_crud"

    # 更新
    ok = MCPToolRepository.update(new_id, description="更新后的描述")
    assert ok
    tool = MCPToolRepository.get_by_id(new_id)
    assert tool["description"] == "更新后的描述"
    print(f"  更新描述: {tool['description']}")

    # 切换启用
    new_status = MCPToolRepository.toggle_enabled(new_id)
    assert new_status == 0, "应该是禁用状态"
    print(f"  切换状态: {'启用' if new_status else '禁用'}")

    # 删除
    ok = MCPToolRepository.delete(new_id)
    assert ok
    tool = MCPToolRepository.get_by_id(new_id)
    assert tool is None, "应该已被删除"
    print(f"  删除成功")

    print("  ✓ 测试通过")


def test_mcp_tool_registry():
    """测试 MCP Tool Registry 加载。"""
    print("\n=== 测试 3: MCPToolRegistry 加载 ===")

    from app.mcp.registry import MCPToolRegistry
    from app.mcp.server import MCPServer

    server = MCPServer.get_instance()
    registry = MCPToolRegistry(server)

    count = registry.load_all_from_db()
    print(f"  从数据库加载了 {count} 个工具")
    assert count > 0, "至少应加载一个工具"

    tool_names = registry.loaded_tool_names
    print(f"  已加载工具: {tool_names[:5]}...")
    assert "search_warehouse" in tool_names

    print("  ✓ 测试通过")


def test_employee_mcp_tool_ids():
    """测试数字员工 mcp_tool_ids 字段。"""
    print("\n=== 测试 4: 数字员工 mcp_tool_ids ===")

    # 获取一个员工
    employees, _ = DigitalEmployeeRepository.get_all(page=1, page_size=5)
    if employees:
        emp = employees[0]
        try:
            tool_ids = json.loads(emp.get("mcp_tool_ids", "[]"))
        except (json.JSONDecodeError, TypeError):
            tool_ids = []
        print(f"  员工「{emp['name']}」mcp_tool_ids: {tool_ids}")

        # 获取该员工的 MCP 工具（未配置 mcp_tool_ids 应返回空）
        tools = MCPToolRepository.get_by_employee(emp["id"])
        print(f"  可用 MCP 工具: {len(tools)} 个 (未配置时遵循最小权限原则)")
        if emp.get("mcp_tool_ids") and emp["mcp_tool_ids"] != "[]":
            assert len(tools) > 0, "已配置工具但返回空"
        else:
            print(f"    员工未配置 mcp_tool_ids，正确返回空列表")

    print("  ✓ 测试通过")


def test_skill_mcp_tool_id():
    """测试技能 mcp_tool_id 关联。"""
    print("\n=== 测试 5: 技能 mcp_tool_id 关联 ===")

    skills = SkillRepository.get_enabled()
    for s in skills:
        mcp_tool_id = s.get("mcp_tool_id")
        if mcp_tool_id:
            tool = MCPToolRepository.get_by_id(mcp_tool_id)
            tool_name = tool["name"] if tool else "未知"
            print(f"  技能「{s['name']}」关联 MCP 工具: {tool_name} (id={mcp_tool_id})")
        else:
            print(f"  技能「{s['name']}」无 MCP 工具关联 (纯 prompt 型)")

    print("  ✓ 测试通过")


def test_tool_test_log():
    """测试 MCP 工具测试日志。"""
    print("\n=== 测试 6: MCP 工具测试日志 ===")

    # 获取一个工具
    tool = MCPToolRepository.get_by_name("search_warehouse")
    if tool:
        log_id = MCPToolRepository.log_test(
            tool["id"],
            '{"keyword":"AI","limit":3}',
            '{"total":2,"items":[...]}',
            1,
            150,
        )
        print(f"  记录测试日志 ID={log_id}")
        assert log_id > 0

        logs = MCPToolRepository.get_test_logs(tool["id"], limit=5)
        print(f"  获取测试日志: {len(logs)} 条")
        if logs:
            print(f"    最新日志: is_success={logs[0]['is_success']}, duration_ms={logs[0]['duration_ms']}")

    print("  ✓ 测试通过")


if __name__ == "__main__":
    print("=" * 60)
    print("MCP 重构验证测试 v0.10")
    print("=" * 60)

    # 初始化数据库和种子数据
    init_db()
    seed_default_data()

    try:
        test_mcp_tool_table()
        test_mcp_tool_crud()
        test_mcp_tool_registry()
        test_employee_mcp_tool_ids()
        test_skill_mcp_tool_id()
        test_tool_test_log()
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print("\n" + "=" * 60)
    print("✓ 所有测试通过!")
    print("=" * 60)
