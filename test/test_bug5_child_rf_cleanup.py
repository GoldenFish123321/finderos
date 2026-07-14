"""
Bug #5: 禁用父功能时子功能的 role_functions 关联残留 — 修复验证

验证: 禁用父功能后，所有子功能的 role_functions 关联也被清理。
相关功能: 启用功能恢复、功能CRUD不受影响。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.function import FunctionRepository
from app.models.role import RoleRepository
from app.models.db import get_db


def setup():
    with get_db() as conn:
        conn.execute("DELETE FROM role_functions WHERE role_id IN (SELECT id FROM roles WHERE name LIKE ?)", ("_bug5_%",))
        conn.execute("DELETE FROM functions WHERE name LIKE ?", ("_bug5_%",))
        conn.execute("DELETE FROM roles WHERE name LIKE ?", ("_bug5_%",))
        conn.commit()


def test_disable_parent_cleans_child_rf():
    """禁用父功能时清理子功能的 role_functions 关联"""
    print("\n=== Bug #5: 禁用父功能清理子功能关联验证 ===")
    setup()

    # 创建测试角色
    RoleRepository.create("_bug5_test_role_", "测试角色")
    role = RoleRepository.get_by_name("_bug5_test_role_")
    role_id = role["id"]
    print(f"  创建测试角色 ID={role_id}")

    # 创建父功能
    parent_id = FunctionRepository.create("_bug5_parent_", icon="layui-icon-test", sort_order=999)
    assert parent_id > 0
    print(f"  创建父功能 ID={parent_id}")

    # 创建子功能
    child_id = FunctionRepository.create("_bug5_child_", parent_id=parent_id, sort_order=999)
    assert child_id > 0
    print(f"  创建子功能 ID={child_id}")

    # 将父功能和子功能都分配给角色
    RoleRepository.set_functions(role_id, [parent_id, child_id])
    func_ids = RoleRepository.get_function_ids(role_id)
    assert parent_id in func_ids, "父功能应已分配"
    assert child_id in func_ids, "子功能应已分配"
    print(f"  角色功能IDs: {func_ids}")

    # 禁用父功能
    status = FunctionRepository.toggle_enabled(parent_id)
    assert status == 0, f"禁用后状态应为0，实际={status}"
    print(f"  父功能已禁用 (status={status})")

    # 验证：父功能的 role_functions 已清理
    func_ids = RoleRepository.get_function_ids(role_id)
    assert parent_id not in func_ids, f"父功能({parent_id})的关联应已清理，实际: {func_ids}"
    print(f"  ✅ 父功能关联已清理")

    # 核心验证：子功能的 role_functions 也应已清理
    assert child_id not in func_ids, f"❌ Bug #5 仍存在: 子功能({child_id})的关联未清理，实际: {func_ids}"
    print(f"  ✅ 子功能关联也已清理")

    # 重新启用父功能
    status = FunctionRepository.toggle_enabled(parent_id)
    assert status == 1, "重新启用后状态应为1"
    print(f"  父功能已重新启用 (status={status})")

    # 验证重新启用后功能本身正常
    func = FunctionRepository.get_by_id(parent_id)
    assert func["is_enabled"] == 1
    func = FunctionRepository.get_by_id(child_id)
    assert func["is_enabled"] == 1  # 子功能本身未被禁用
    print(f"  ✅ 重新启用后功能状态正常")

    setup()
    print("  ✅ Bug #5 修复验证通过")


def test_function_toggle_basic():
    """验证基本启停功能不受影响"""
    print("\n  --- 验证相关功能: 基本启停 ---")
    setup()

    fid = FunctionRepository.create("_bug5_toggle_", sort_order=998)
    assert fid > 0

    # 禁用
    status = FunctionRepository.toggle_enabled(fid)
    assert status == 0
    func = FunctionRepository.get_by_id(fid)
    assert func["is_enabled"] == 0
    print(f"  ✅ 禁用功能: status={status}")

    # 启用
    status = FunctionRepository.toggle_enabled(fid)
    assert status == 1
    func = FunctionRepository.get_by_id(fid)
    assert func["is_enabled"] == 1
    print(f"  ✅ 启用功能: status={status}")

    # 不存在的功能
    status = FunctionRepository.toggle_enabled(99999)
    assert status == -1
    print(f"  ✅ 不存在功能: status={status}")

    # 清理
    FunctionRepository.delete(fid)
    print("  ✅ 基本启停正常")


def test_function_tree_unaffected():
    """验证功能树不受影响"""
    print("\n  --- 验证相关功能: 功能树 ---")

    tree = FunctionRepository.get_tree()
    assert len(tree) > 0
    print(f"  ✅ 功能树: {len(tree)} 个顶级节点")

    enabled_tree = FunctionRepository.get_enabled_tree()
    assert len(enabled_tree) > 0
    print(f"  ✅ 启用功能树: {len(enabled_tree)} 个顶级节点")

    # 获取所有功能
    all_funcs, total = FunctionRepository.get_all(page=1, page_size=100)
    assert total > 0
    print(f"  ✅ 功能总数: {total}")

    print("  ✅ 功能树正常")


if __name__ == "__main__":
    print("=" * 60)
    print("  Bug #5 修复验证")
    print("=" * 60)

    try:
        test_disable_parent_cleans_child_rf()
        test_function_toggle_basic()
        test_function_tree_unaffected()
        print("\n" + "=" * 60)
        print("  ✅ Bug #5 全部验证通过！")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n❌ 验证失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
