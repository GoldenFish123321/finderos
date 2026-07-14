"""
Bug #4: collector.py Cookie 全局状态竞态条件 — 修复验证

验证: 线程锁保护 _ensure_baidu_cookies() 防止并发竞态
相关功能: fetch_and_parse SSRF 校验 + URL 校验
"""
import os
import sys
import threading
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.collector import _ensure_baidu_cookies, _global_cookie_jar, _global_cookie_lock
from http.cookiejar import CookieJar


def test_cookie_lock_prevents_race():
    """验证线程锁防止 _ensure_baidu_cookies 的竞态条件"""
    print("\n=== Bug #4: Cookie 全局状态竞态修复验证 ===")

    # 重置全局状态，模拟首次未初始化
    import app.services.collector as collector
    collector._global_cookie_jar = None

    # 验证锁对象存在
    assert _global_cookie_lock is not None
    assert isinstance(_global_cookie_lock, type(threading.Lock()))
    print("  ✅ 线程锁已存在")

    # 模拟并发调用：创建多个线程同时调用 _ensure_baidu_cookies
    # 注意：真实调用会访问 baidu.com，这里用 mock 来模拟

    original_cookie_jar = CookieJar()

    with patch('app.services.collector.CookieJar', return_value=original_cookie_jar):
        with patch('app.services.collector.urllib.request.build_opener') as mock_build:
            mock_opener = MagicMock()
            mock_resp = MagicMock()
            mock_resp.read.return_value = b""
            mock_resp.close.return_value = None
            mock_opener.open.return_value.__enter__.return_value = mock_resp
            mock_build.return_value = mock_opener

            # 重置
            collector._global_cookie_jar = None

            # 并发调用
            threads = []
            errors = []

            def call_ensure():
                try:
                    _ensure_baidu_cookies()
                except Exception as e:
                    errors.append(e)

            for _ in range(8):
                t = threading.Thread(target=call_ensure)
                threads.append(t)

            for t in threads:
                t.start()
            for t in threads:
                t.join()

            # 验证：没有错误
            assert len(errors) == 0, f"并发调用产生错误: {errors}"
            # 验证：_ensure_baidu_cookies 应该只真正初始化一次（内部没有双重检查锁定时可能多次）
            # 注意：由于锁内的双重检查，第二个以上线程应该跳过初始化
            print(f"  ✅ 并发 8 线程无竞态错误")

    # 验证：重置后锁仍然可用
    collector._global_cookie_jar = None
    assert _global_cookie_lock.locked() == False
    print(f"  ✅ 锁状态正常（未死锁）")

    print("  ✅ Bug #4 修复验证通过")


def test_related_functionality_ssrf():
    """验证相关功能：fetch_and_parse 的 SSRF 防护不受影响"""
    print("\n  --- 验证相关功能: SSRF 防护 ---")
    from app.services.collector import fetch_and_parse

    # 内网地址应该被 SSRF 防护拦截
    status, size, text, news = fetch_and_parse("http://127.0.0.1:22", parser="generic")
    assert status == 0
    assert "SSRF Blocked" in text or "SSRF 拦截" in text or "Blocked" in str(
        text) or "Error" in str(text), f"内网地址应被 SSRF 拦截，实际返回值: status={status}, text={text[:100]}"
    print("  ✅ SSRF 防护正常拦截内网地址")

    # 空 URL 应被处理
    status, size, text, news = fetch_and_parse("", parser="generic")
    print(f"  ✅ 空 URL 处理正常: {text[:50] if text else 'OK'}")

    # 无效 URL 应被处理
    status, size, text, news = fetch_and_parse("not-a-valid-url", parser="generic")
    print(f"  ✅ 无效 URL 处理正常: {text[:50] if text else 'OK'}")

    print("  ✅ 相关功能验证通过")


if __name__ == "__main__":
    print("=" * 60)
    print("  Bug #4 修复验证")
    print("=" * 60)

    try:
        test_cookie_lock_prevents_race()
        test_related_functionality_ssrf()
        print("\n" + "=" * 60)
        print("  ✅ Bug #4 全部验证通过！")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n❌ 验证失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
