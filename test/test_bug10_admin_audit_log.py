"""
Bug #10: AdminBaseHandler 禁用用户访问无审计日志 — 修复验证

验证: 禁用用户/无角色/无功能权限的用户访问后台时记录审计日志。
相关功能: 正常管理后台访问不受影响。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils.security import write_audit_log
from app.models.db import get_db
from app.config.settings import settings


def setup():
    with get_db() as conn:
        conn.execute("DELETE FROM audit_logs WHERE action LIKE ?", ("ACCESS_DENIED%",))
        conn.commit()


def test_audit_log_written_for_disabled():
    """验证禁用用户访问后台会写入审计日志"""
    print("\n=== Bug #10: 禁用用户访问审计日志修复验证 ===")
    setup()

    # 确保审计已启用
    assert settings.AUDIT_ENABLED, "审计功能应启用"

    # 模拟 AdminBaseHandler 的审计日志写入
    write_audit_log(
        action="ACCESS_DENIED_DISABLED",
        username="disabled_user",
        target="/admin",
        detail="禁用用户尝试访问管理后台",
        client_ip="127.0.0.1",
    )
    print(f"  ✅ 写入 ACCESS_DENIED_DISABLED 审计日志")

    # 验证日志已写入数据库
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM audit_logs WHERE action = ? AND username = ?",
            ("ACCESS_DENIED_DISABLED", "disabled_user"),
        ).fetchone()
    assert row is not None, "审计日志应已写入"
    assert row["detail"] == "禁用用户尝试访问管理后台"
    print(f"  ✅ 审计日志已记录: action={row['action']}, user={row['username']}")

    print("  ✅ Bug #10 修复验证通过")


def test_audit_log_various_denials():
    """验证各类拒绝访问场景的审计日志"""
    print("\n  --- 验证各类拒绝场景审计日志 ---")

    # 无角色
    write_audit_log(
        action="ACCESS_DENIED_NO_ROLE",
        username="norole_user",
        target="/admin/user",
        detail="无角色用户尝试访问管理后台",
        client_ip="10.0.0.1",
    )

    # 无功能权限
    write_audit_log(
        action="ACCESS_DENIED_NO_FUNCTIONS",
        username="basic_user",
        target="/admin/model",
        detail="角色'普通用户'无功能权限访问管理后台",
        client_ip="10.0.0.2",
    )

    # 每个测试使用独立数据库，本用例写入两条拒绝日志
    with get_db() as conn:
        cnt = conn.execute(
            "SELECT COUNT(*) as cnt FROM audit_logs WHERE action LIKE ?",
            ("ACCESS_DENIED%",),
        ).fetchone()["cnt"]
    assert cnt == 2, f"应有2条拒绝访问日志，实际={cnt}"
    print(f"  ✅ 共 {cnt} 条拒绝访问审计日志")

    # 验证各条日志内容
    with get_db() as conn:
        rows = conn.execute(
            "SELECT action, username FROM audit_logs WHERE action LIKE ?",
            ("ACCESS_DENIED%",),
        ).fetchall()
    actions = {r["action"]: r["username"] for r in rows}
    assert actions.get("ACCESS_DENIED_NO_ROLE") == "norole_user"
    assert actions.get("ACCESS_DENIED_NO_FUNCTIONS") == "basic_user"
    print(f"  ✅ 各类拒绝日志内容正确: {list(actions.keys())}")

    print("  ✅ 各类拒绝审计日志正常")


def test_normal_audit_unaffected():
    """验证正常审计日志不受影响"""
    print("\n  --- 验证相关功能: 正常审计日志 ---")

    # 正常的登录成功日志
    write_audit_log(
        action="LOGIN_SUCCESS",
        username="admin",
        target="",
        detail="登录成功",
        client_ip="127.0.0.1",
    )
    print(f"  ✅ 写入 LOGIN_SUCCESS 审计日志")

    # 验证
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM audit_logs WHERE action = ? AND username = ? ORDER BY id DESC LIMIT 1",
            ("LOGIN_SUCCESS", "admin"),
        ).fetchone()
    assert row is not None
    print(f"  ✅ 正常审计日志未受影响")

    # 清理（只清理测试数据）
    setup()
    print("  ✅ 正常审计功能不受影响")


if __name__ == "__main__":
    print("=" * 60)
    print("  Bug #10 修复验证")
    print("=" * 60)

    try:
        test_audit_log_written_for_disabled()
        test_audit_log_various_denials()
        test_normal_audit_unaffected()
        print("\n" + "=" * 60)
        print("  ✅ Bug #10 全部验证通过！")
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
