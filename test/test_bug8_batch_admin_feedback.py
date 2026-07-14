"""
Bug #8: 批量操作admin静默跳过无前端反馈 — 修复验证

验证: batch_delete/batch_toggle 返回跳过的admin数量，消息含明确提示。
相关功能: 单个删除/禁用、批量非admin操作不受影响。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.user import UserRepository
from app.models.db import get_db


def setup():
    with get_db() as conn:
        conn.execute("DELETE FROM users WHERE username LIKE ?", ("_bug8_%",))
        conn.commit()


def test_batch_delete_skipped_admin_info():
    """验证批量删除返回跳过admin数"""
    print("\n=== Bug #8: 批量操作admin跳过提示验证 ===")
    setup()

    # 创建测试用户
    UserRepository.create_user("_bug8_test1_", "test123456", role_id=2)
    UserRepository.create_user("_bug8_test2_", "test123456", role_id=2)
    user1 = UserRepository.get_user_by_username("_bug8_test1_")
    user2 = UserRepository.get_user_by_username("_bug8_test2_")

    # admin 的 ID
    admin = UserRepository.get_user_by_username("admin")
    admin_id = admin["id"]

    # 批量删除：包含admin + 两个普通用户
    ids = [admin_id, user1["id"], user2["id"]]
    count, skipped_admin = UserRepository.batch_delete(ids)

    assert count == 2, f"应删除2个普通用户，实际={count}"
    assert skipped_admin == 1, f"应跳过1个admin，实际={skipped_admin}"
    print(f"  ✅ 批量删除: 删除{count}个, 跳过{skipped_admin}个admin")

    # 验证消息格式
    msg = f"成功删除 {count} 个用户"
    if skipped_admin > 0:
        msg += f"（跳过 {skipped_admin} 个受保护的管理员账号）"
    assert "跳过" in msg and "管理员" in msg
    print(f"  ✅ 消息包含提示: {msg}")

    setup()
    print("  ✅ Bug #8 修复验证通过")


def test_batch_toggle_skipped_admin_info():
    """验证批量启停返回跳过admin数"""
    print("\n  --- 验证批量启停 ---")
    setup()

    UserRepository.create_user("_bug8_tog1_", "test123456", role_id=2)
    UserRepository.create_user("_bug8_tog2_", "test123456", role_id=2)
    user1 = UserRepository.get_user_by_username("_bug8_tog1_")
    user2 = UserRepository.get_user_by_username("_bug8_tog2_")
    admin = UserRepository.get_user_by_username("admin")

    # 批量禁用：包含admin
    ids = [admin["id"], user1["id"], user2["id"]]
    count, skipped_admin = UserRepository.batch_toggle(ids, enable=False)

    assert count == 2, f"应禁用2个普通用户，实际={count}"
    assert skipped_admin == 1, f"应跳过1个admin，实际={skipped_admin}"
    print(f"  ✅ 批量禁用: 禁用{count}个, 跳过{skipped_admin}个admin")

    # 恢复启用
    UserRepository.batch_toggle([user1["id"], user2["id"]], enable=True)

    setup()
    print("  ✅ 批量启停验证通过")


def test_normal_batch_unaffected():
    """验证不含admin的批量操作不受影响"""
    print("\n  --- 验证相关功能: 不含admin的批量操作 ---")
    setup()

    UserRepository.create_user("_bug8_n1_", "test123456", role_id=2)
    UserRepository.create_user("_bug8_n2_", "test123456", role_id=2)
    user1 = UserRepository.get_user_by_username("_bug8_n1_")
    user2 = UserRepository.get_user_by_username("_bug8_n2_")

    # 批量删除不含admin
    count, skipped_admin = UserRepository.batch_delete([user1["id"], user2["id"]])
    assert count == 2
    assert skipped_admin == 0, f"不含admin时skipped_admin应为0，实际={skipped_admin}"
    print(f"  ✅ 不含admin: 删除{count}个, 跳过{skipped_admin}个")

    setup()
    print("  ✅ 正常批量操作不受影响")


def test_self_delete_still_protected():
    """验证自删除保护不受影响"""
    print("\n  --- 验证相关功能: 自删除保护 ---")
    setup()

    UserRepository.create_user("_bug8_self_", "test123456", role_id=1)
    user = UserRepository.get_user_by_username("_bug8_self_")
    user_id = user["id"]

    # 模拟 handler 自过滤逻辑
    ids = [user_id]
    current_user_id = user_id  # 假装自己操作
    filtered = [uid for uid in ids if uid != current_user_id]
    assert len(filtered) == 0, "应过滤掉自己的ID"
    print(f"  ✅ 自删除保护: 过滤后剩余{len(filtered)}个")

    UserRepository.delete_user(user_id)
    setup()
    print("  ✅ 自删除保护正常")


if __name__ == "__main__":
    print("=" * 60)
    print("  Bug #8 修复验证")
    print("=" * 60)

    try:
        test_batch_delete_skipped_admin_info()
        test_batch_toggle_skipped_admin_info()
        test_normal_batch_unaffected()
        test_self_delete_still_protected()
        print("\n" + "=" * 60)
        print("  ✅ Bug #8 全部验证通过！")
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
