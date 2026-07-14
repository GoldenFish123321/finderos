"""
Bug #12: update_user/delete 使用 total_changes 不可靠 — 修复验证

验证: 改为 cursor.rowcount 精确判断影响行数
相关功能: 用户/功能 CRUD 不受影响
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.user import UserRepository
from app.models.function import FunctionRepository
from app.models.db import get_db


def test_rowcount_accuracy():
    """验证 rowcount 能准确反映实际影响行数"""
    print("\n=== Bug #12: rowcount 精确性验证 ===")

    # 用户删除
    UserRepository.create_user("_bug12_del_", "test123456")
    user = UserRepository.get_user_by_username("_bug12_del_")
    user_id = user["id"]
    ok = UserRepository.delete_user(user_id)
    assert ok
    # 再删除一次应该返回 False
    ok = UserRepository.delete_user(user_id)
    assert not ok, "删除不存在的用户应返回 False"
    print("  ✅ 用户删除 rowcount 精确")

    # 更新不存在的用户
    ok = UserRepository.update_user(99999, "nonexistent")
    assert not ok, "更新不存在的用户应返回 False"
    print("  ✅ 用户更新 rowcount 精确")

    # 功能删除（含子节点）
    # 先创建一个父功能和一个子功能
    parent_id = FunctionRepository.create("_bug12_parent_", sort_order=999)
    child_id = FunctionRepository.create("_bug12_child_", parent_id=parent_id, sort_order=999)

    # 验证父功能存在
    assert FunctionRepository.get_by_id(parent_id) is not None
    assert FunctionRepository.get_by_id(child_id) is not None

    # 删除父功能（级联删除子节点）
    ok = FunctionRepository.delete(parent_id)
    assert ok, "删除功能应成功"
    # 验证已删除
    assert FunctionRepository.get_by_id(parent_id) is None
    assert FunctionRepository.get_by_id(child_id) is None
    print("  ✅ 功能删除（含子节点）rowcount 精确")

    # 删除不存在的功能
    ok = FunctionRepository.delete(99999)
    assert not ok, "删除不存在的功能应返回 False"
    print("  ✅ 删除不存在功能返回 False")

    # 清理
    with get_db() as conn:
        conn.execute("DELETE FROM users WHERE username LIKE ?", ("_bug12_%",))
        conn.execute("DELETE FROM functions WHERE name LIKE ?", ("_bug12_%",))
        conn.commit()

    print("  ✅ Bug #12 修复验证通过")


def test_related_functionality():
    """验证相关功能不受影响"""
    print("\n  --- 验证相关功能: CRUD 操作 ---")

    # 用户 CRUD
    ok = UserRepository.create_user("_bug12_crud_", "test123456", role_id=2)
    assert ok
    user = UserRepository.get_user_by_username("_bug12_crud_")
    ok = UserRepository.update_user(user["id"], "_bug12_crud_", "newpass", role_id=1)
    assert ok
    assert UserRepository.verify_user("_bug12_crud_", "newpass")
    ok = UserRepository.delete_user(user["id"])
    assert ok
    print("  ✅ 用户 CRUD 正常")

    # 功能 CRUD
    fid = FunctionRepository.create("_bug12_func_", sort_order=998)
    assert fid > 0
    func = FunctionRepository.get_by_id(fid)
    ok = FunctionRepository.update(fid, "_bug12_func_updated_", sort_order=998)
    assert ok
    ok = FunctionRepository.delete(fid)
    assert ok
    print("  ✅ 功能 CRUD 正常")

    # 分页查询
    rows, total = UserRepository.get_all(page=1, page_size=100)
    assert total >= 0
    rows, total = FunctionRepository.get_all(page=1, page_size=100)
    assert total >= 0
    print("  ✅ 分页查询正常")

    with get_db() as conn:
        conn.execute("DELETE FROM users WHERE username LIKE ?", ("_bug12_%",))
        conn.execute("DELETE FROM functions WHERE name LIKE ?", ("_bug12_%",))
        conn.commit()

    print("  ✅ 相关功能验证通过")


if __name__ == "__main__":
    print("=" * 60)
    print("  Bug #12 修复验证")
    print("=" * 60)

    try:
        test_rowcount_accuracy()
        test_related_functionality()
        print("\n" + "=" * 60)
        print("  ✅ Bug #12 全部验证通过！")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n❌ 验证失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
