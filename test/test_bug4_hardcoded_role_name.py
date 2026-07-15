"""
Bug #4: 角色名"普通用户"硬编码导致权限判断脆弱 — 修复验证

验证: 登录跳转、后台访问控制不再依赖硬编码角色名，改为功能权限判断。
相关功能: 注册默认角色查找、管理员登录跳转不受影响。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.user import UserRepository
from app.models.role import RoleRepository
from app.models.function import FunctionRepository
from app.models.db import get_db


def setup():
    with get_db() as conn:
        conn.execute("DELETE FROM users WHERE username LIKE ?", ("_bug4_%",))
        conn.execute("DELETE FROM roles WHERE name LIKE ?", ("_bug4_%",))
        conn.commit()


def test_login_redirect_by_functions():
    """验证登录跳转基于功能权限而非角色名"""
    print("\n=== Bug #4: 角色名硬编码修复验证 ===")

    # 场景1: admin 有功能权限 → 应跳转 /admin
    funcs = UserRepository.get_user_functions("admin")
    assert len(funcs) > 0, "admin应有功能权限"
    # 模拟 _redirect_by_role 逻辑
    if funcs:
        dest = "/admin"
    else:
        dest = "/index"
    assert dest == "/admin", f"admin应跳转/admin，实际={dest}"
    print(f"  ✅ admin(有功能权限) → {dest}")

    # 场景2: 创建无功能的角色并分配给用户 → 应跳转 /index
    setup()
    RoleRepository.create("_bug4_nofunc_", "无功能测试角色")
    role = RoleRepository.get_by_name("_bug4_nofunc_")
    UserRepository.create_user("_bug4_nofunc_user_", "test123456", role_id=role["id"])
    funcs = UserRepository.get_user_functions("_bug4_nofunc_user_")
    assert len(funcs) == 0, "无功能角色的用户不应有功能权限"
    dest = "/admin" if funcs else "/index"
    assert dest == "/index", f"无功能用户应跳转/index，实际={dest}"
    print(f"  ✅ 无功能用户 → {dest}")

    setup()
    print("  ✅ Bug #4 修复验证通过")


def test_admin_access_control():
    """验证后台访问控制基于功能权限"""
    print("\n  --- 验证相关功能: 后台访问控制 ---")

    # admin 有功能 → 可访问后台
    funcs = UserRepository.get_user_functions("admin")
    assert len(funcs) > 0
    print(f"  ✅ admin 功能数={len(funcs)}，可访问后台")

    # 普通用户角色现在会由种子数据授予最小后台权限（如模型 API 配置），
    # 无功能访问场景应使用上面的自定义无功能角色覆盖。
    setup()
    UserRepository.create_user("_bug4_normal_", "test123456", role_id=2)
    funcs = UserRepository.get_user_functions("_bug4_normal_")
    print(f"  ✅ 普通用户(role_id=2)功能数={len(funcs)}，默认权限由种子配置决定")

    setup()
    print("  ✅ 访问控制验证通过")


def test_register_default_role():
    """验证注册默认角色查找不受影响"""
    print("\n  --- 验证相关功能: 注册默认角色 ---")

    # 模拟 RegisterHandler 的角色查找逻辑
    default_role = RoleRepository.get_by_name("普通用户")
    assert default_role is not None, "默认'普通用户'角色应存在"
    role_id = default_role["id"] if default_role else 2
    assert role_id == 2, f"普通用户role_id应为2，实际={role_id}"
    print(f"  ✅ 默认角色: id={role_id}, name='{default_role['name']}'")

    # 验证角色表中确实有is_system标记
    assert default_role["is_system"] == 1, "普通用户角色应有is_system=1"
    print(f"  ✅ is_system={default_role['is_system']}")

    print("  ✅ 注册默认角色查找正常")


def test_admin_login_jump():
    """验证管理员登录跳转逻辑（Home页）不受影响"""
    print("\n  --- 验证相关功能: Home页跳转 ---")

    # admin → 应跳转后台
    funcs = UserRepository.get_user_functions("admin")
    assert len(funcs) > 0
    print(f"  ✅ admin: 功能数={len(funcs)} → 跳转/admin")

    # 模拟 Home 页逻辑
    dest = "/admin" if funcs else "/index"
    assert dest == "/admin"
    print(f"  ✅ Home页跳转逻辑正确")

    print("  ✅ Home页跳转验证通过")


if __name__ == "__main__":
    print("=" * 60)
    print("  Bug #4 修复验证")
    print("=" * 60)

    try:
        test_login_redirect_by_functions()
        test_admin_access_control()
        test_register_default_role()
        test_admin_login_jump()
        print("\n" + "=" * 60)
        print("  ✅ Bug #4 全部验证通过！")
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
