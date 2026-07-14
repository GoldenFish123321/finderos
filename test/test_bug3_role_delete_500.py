"""
Bug #3: RoleRepository.delete 无异常处理导致500错误 — 修复验证

验证: 有关联用户的角色删除会返回False而非触发IntegrityError
相关功能: 系统角色保护、角色CRUD不受影响
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.role import RoleRepository
from app.models.user import UserRepository
from app.models.db import get_db


def setup():
    with get_db() as conn:
        conn.execute("DELETE FROM users WHERE username LIKE ?", ("_bug3_%",))
        conn.execute("DELETE FROM roles WHERE name LIKE ?", ("_bug3_%",))
        conn.commit()


def test_delete_role_with_users():
    """验证有关联用户的角色删除返回False（不抛异常）"""
    print("\n=== Bug #3: 角色删除异常处理修复验证 ===")
    setup()

    # 创建测试角色
    ok = RoleRepository.create("_bug3_test_role_", "测试角色")
    assert ok, "创建测试角色失败"
    role = RoleRepository.get_by_name("_bug3_test_role_")
    role_id = role["id"]
    print(f"  创建测试角色 ID={role_id}")

    # 创建关联该角色的测试用户
    ok = UserRepository.create_user("_bug3_role_user_", "test123456", role_id=role_id)
    assert ok, "创建测试用户失败"
    print(f"  创建关联用户成功")

    # 尝试删除有关联用户的角色 — 应返回False，不抛异常
    try:
        result = RoleRepository.delete(role_id)
        assert not result, f"有关联用户的角色删除应返回False，实际={result}"
        print(f"  ✅ 有关联用户时删除返回 False（不抛异常）")
    except Exception as e:
        print(f"  ❌ BUG仍存在: 抛出异常 {type(e).__name__}: {e}")
        assert False, f"Bug #3 未修复: {e}"

    # 清理用户后再删除
    user = UserRepository.get_user_by_username("_bug3_role_user_")
    UserRepository.delete_user(user["id"])
    result = RoleRepository.delete(role_id)
    assert result, "解除关联后删除应成功"
    print(f"  ✅ 解除关联后删除成功: {result}")

    # 验证角色已不存在
    role_after = RoleRepository.get_by_id(role_id)
    assert role_after is None, "角色应已被删除"
    print(f"  ✅ 验证角色已删除")

    setup()
    print("  ✅ Bug #3 修复验证通过")


def test_system_role_protection():
    """验证系统角色保护不受影响"""
    print("\n  --- 验证相关功能: 系统角色保护 ---")

    # 系统管理员(ID=1)不可删除
    ok = RoleRepository.delete(1)
    assert not ok, "系统角色(ID=1)应不可删除"
    print(f"  ✅ 系统管理员(ID=1)不可删除: {not ok}")

    # 普通用户(ID=2)不可删除
    ok = RoleRepository.delete(2)
    assert not ok, "普通用户角色(ID=2)应不可删除"
    print(f"  ✅ 普通用户角色(ID=2)不可删除: {not ok}")

    print("  ✅ 系统角色保护正常")


def test_role_crud_unaffected():
    """验证角色 CRUD 不受影响"""
    print("\n  --- 验证相关功能: 角色 CRUD ---")
    setup()

    # 创建
    ok = RoleRepository.create("_bug3_crud_", "crud测试")
    assert ok
    role = RoleRepository.get_by_name("_bug3_crud_")
    role_id = role["id"]
    print(f"  ✅ 创建角色: ID={role_id}")

    # 更新
    ok = RoleRepository.update(role_id, "_bug3_crud_updated_", "已更新")
    assert ok
    role = RoleRepository.get_by_id(role_id)
    assert role["description"] == "已更新"
    print(f"  ✅ 更新角色: {role['name']}")

    # 删除
    ok = RoleRepository.delete(role_id)
    assert ok
    assert RoleRepository.get_by_id(role_id) is None
    print(f"  ✅ 删除角色成功")

    # 分页查询
    rows, total = RoleRepository.get_all(page=1, page_size=10)
    assert total > 0
    print(f"  ✅ 分页查询: {total} 个角色")

    setup()
    print("  ✅ 角色 CRUD 正常")


if __name__ == "__main__":
    print("=" * 60)
    print("  Bug #3 修复验证")
    print("=" * 60)

    try:
        test_delete_role_with_users()
        test_system_role_protection()
        test_role_crud_unaffected()
        print("\n" + "=" * 60)
        print("  ✅ Bug #3 全部验证通过！")
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
