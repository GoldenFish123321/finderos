"""
Bug #6: LoginRateLimiter.record_failure 不清理过期条目 — 修复验证

验证: record_failure 在记录前会清理所有过期记录，防止内存泄漏。
相关功能: check逻辑、登录限速不受影响。
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.controllers.auth import LoginRateLimiter
from app.config.settings import settings


def test_record_failure_cleans_expired():
    """验证 record_failure 会清理过期条目"""
    print("\n=== Bug #6: record_failure 清理过期条目验证 ===")

    limiter = LoginRateLimiter(scope="test_bug6")

    # 注入一个"已过期"的失败记录（模拟超过锁定期的情况）
    old_time = time.time() - settings.LOGIN_LOCKOUT_SECONDS - 60
    limiter._failures[("1.1.1.1", "expired_user")] = (5, old_time)

    assert ("1.1.1.1", "expired_user") in limiter._failures
    print(f"  注入过期记录: {len(limiter._failures)} 条")

    # 调用 record_failure — 应该清理过期记录
    limiter.record_failure("2.2.2.2", "new_user")

    # 过期记录应被清理
    assert ("1.1.1.1", "expired_user") not in limiter._failures, \
        "❌ Bug #6 仍存在: 过期记录未被清理"
    print(f"  ✅ 过期记录已清理: 剩余 {len(limiter._failures)} 条")

    # 新记录应正常存在
    assert ("2.2.2.2", "new_user") in limiter._failures
    count = limiter._failures[("2.2.2.2", "new_user")][0]
    assert count == 1, f"新记录计数应为1，实际={count}"
    print(f"  ✅ 新记录正常: count={count}")

    print("  ✅ Bug #6 修复验证通过")


def test_check_still_cleans():
    """验证 check 方法的清理功能不受影响"""
    print("\n  --- 验证相关功能: check 清理 ---")

    limiter = LoginRateLimiter(scope="test_bug6_check")
    old_time = time.time() - settings.LOGIN_LOCKOUT_SECONDS - 120
    limiter._failures[("3.3.3.3", "old_user")] = (3, old_time)

    ok, msg = limiter.check("4.4.4.4", "any_user")
    assert ok, "未锁定时应允许"
    # check 应清理过期记录
    assert ("3.3.3.3", "old_user") not in limiter._failures
    print(f"  ✅ check 仍清理过期记录")

    print("  ✅ check 功能正常")


def test_rate_limiter_full_flow():
    """验证完整登录限速流程不受影响"""
    print("\n  --- 验证相关功能: 完整限速流程 ---")

    limiter = LoginRateLimiter(scope="test_bug6_flow")
    ip, username = "5.5.5.5", "flow_user"

    # 初始状态允许
    ok, _ = limiter.check(ip, username)
    assert ok

    # 记录几次失败
    for _ in range(settings.LOGIN_MAX_FAILURES - 1):
        limiter.record_failure(ip, username)

    # 仍应允许（未达阈值）
    ok, _ = limiter.check(ip, username)
    assert ok, f"失败{settings.LOGIN_MAX_FAILURES-1}次应仍允许"
    print(f"  ✅ {settings.LOGIN_MAX_FAILURES-1}次失败后仍允许")

    # 达到阈值
    limiter.record_failure(ip, username)
    ok, msg = limiter.check(ip, username)
    assert not ok
    assert "秒后再试" in msg
    print(f"  ✅ 达到阈值后被锁定: {msg[:30]}...")

    # 清除后应允许
    limiter.clear(ip, username)
    ok, _ = limiter.check(ip, username)
    assert ok
    print(f"  ✅ 清除后允许登录")

    print("  ✅ 完整限速流程正常")


if __name__ == "__main__":
    print("=" * 60)
    print("  Bug #6 修复验证")
    print("=" * 60)

    try:
        test_record_failure_cleans_expired()
        test_check_still_cleans()
        test_rate_limiter_full_flow()
        print("\n" + "=" * 60)
        print("  ✅ Bug #6 全部验证通过！")
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
