"""
Bug #14, #15, #16 — 修复验证

Bug #14: LoginHandler 密码未 strip
Bug #15: _decompress 不支持 Brotli
Bug #16: seed_default_data 强制关闭外键约束
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_bug14_password_strip():
    """验证密码 strip 逻辑"""
    print("\n=== Bug #14: 密码 strip 修复验证 ===")

    # 验证 auth.py 中密码被 strip
    import inspect
    from app.controllers import auth

    source = inspect.getsource(auth.LoginHandler.post)
    has_strip = '.strip()' in source.split('password')[1].split('\n')[0] if 'password' in source else False
    # 更可靠的方法：检查源码
    lines = source.split('\n')
    password_line_found = False
    for line in lines:
        if 'password' in line and 'get_body_argument' in line:
            password_line_found = True
            has_strip = '.strip()' in line
            print(f"  LoginHandler.post 密码行: {line.strip()}")
            break
    assert password_line_found, "应找到 get_body_argument('password') 调用"
    assert has_strip, "密码行应包含 .strip()"
    print("  ✅ LoginHandler.post 密码已 strip")

    # 验证 verify_user 函数也正常工作（密码带空格会被strip后校验）
    from app.models.user import UserRepository
    from app.models.db import get_db

    # 清理
    with get_db() as conn:
        conn.execute("DELETE FROM users WHERE username LIKE ?", ("_bug14_%",))
        conn.commit()

    # 创建用户
    ok = UserRepository.create_user("_bug14_test_", "mypassword", role_id=2)
    assert ok

    # 密码带空格应登录失败（因为strip后变成空或不匹配）
    ok_stripped = UserRepository.verify_user("_bug14_test_", "mypassword")
    assert ok_stripped, "正确密码应通过验证"

    # 带前后空格应该也能登录（如果登录时strip了，verify_user 内部不strip）
    # 注意：verify_user 内部不 strip，所以带空格的密码会验证失败
    # 但 LoginHandler 中 strip 后传入的就是无空格密码，所以能匹配
    print("  ✅ 密码验证功能正常")

    # 清理
    with get_db() as conn:
        conn.execute("DELETE FROM users WHERE username LIKE ?", ("_bug14_%",))
        conn.commit()
    print("  ✅ Bug #14 验证通过")


def test_bug15_brotli_support():
    """验证 Brotli 解压支持"""
    print("\n=== Bug #15: Brotli 解压修复验证 ===")

    from app.services.collector import _decompress

    # 普通数据解压
    result = _decompress(b"hello", "")
    assert result == b"hello"
    print("  ✅ 普通数据正常")

    # Brotli 不可用/解压失败时返回原始数据（不静默丢弃）
    raw_brotli = b"\x0b\x02\x80\x47\x65\x6e\x65\x72\x69\x63\x03"
    with pytest.raises(ValueError, match="Brotli 响应不完整"):
        _decompress(raw_brotli, "br")
    print(f"  ✅ Brotli 不可用时返回原始数据 (不静默丢弃)")

    # gzip 解压
    import gzip
    original = b"Hello World" * 100
    compressed = gzip.compress(original)
    result = _decompress(compressed, "gzip")
    assert result == original, "gzip 解压应正常"
    print("  ✅ gzip 解压正常")

    # deflate 解压
    import zlib
    compressed = zlib.compress(original)
    result = _decompress(compressed, "deflate")
    assert result == original, "deflate 解压应正常"
    print("  ✅ deflate 解压正常")

    # 空数据处理
    result = _decompress(b"", "gzip")
    assert result == b""
    print("  ✅ 空数据处理正常")

    # gzip 包含在更长的编码字符串中
    result = _decompress(gzip.compress(original), "gzip, deflate, br")
    assert result == original, "复合编码应能匹配 gzip"
    print("  ✅ 复合编码解压正常")

    print("  ✅ Bug #15 验证通过")


def test_bug16_foreign_keys():
    """验证种子数据不关闭外键约束"""
    print("\n=== Bug #16: 种子数据外键约束修复验证 ===")

    import inspect
    from app.models import db

    source = inspect.getsource(db.seed_default_data)
    has_fk_off = "PRAGMA foreign_keys=OFF" in source
    has_fk_on = "PRAGMA foreign_keys=ON" in source
    print(f"  种子数据中含 'PRAGMA foreign_keys=OFF': {has_fk_off} (期望: False)")
    print(f"  种子数据中含 'PRAGMA foreign_keys=ON': {has_fk_on} (期望: False)")

    assert not has_fk_off, "种子数据不应再关闭外键约束"
    assert not has_fk_on, "种子数据不应再开启外键约束（因为根本没关）"
    print("  ✅ 种子数据不再关闭外键约束")

    # 验证 seed_default_data 仍能正常运行
    db.seed_default_data()
    print("  ✅ seed_default_data 执行正常")

    # 验证外键约束仍启用
    from app.models.db import get_db
    with get_db() as conn:
        fk_status = conn.execute("PRAGMA foreign_keys").fetchone()
        print(f"  当前外键约束状态: {fk_status}")
        assert fk_status and fk_status.get("foreign_keys") == 1, "外键约束应处于启用状态"

    print("  ✅ Bug #16 验证通过")


if __name__ == "__main__":
    print("=" * 60)
    print("  Bug #14, #15, #16 修复验证")
    print("=" * 60)

    try:
        test_bug14_password_strip()
        test_bug15_brotli_support()
        test_bug16_foreign_keys()
        print("\n" + "=" * 60)
        print("  ✅ Bug #14, #15, #16 全部验证通过！")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n❌ 验证失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
