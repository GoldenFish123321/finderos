"""
Bug #7: WatchHandler.post() 未做URL去重 — 修复验证

验证: create_if_not_exists 会跳过重复URL的采集结果。
相关功能: 瞭望采集、保存流程不受影响。
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.watch_result import WatchResultRepository
from app.models.db import get_db


def setup():
    with get_db() as conn:
        conn.execute("DELETE FROM watch_results WHERE keyword LIKE ?", ("%bug7%",))
        conn.commit()


def test_url_dedup():
    """验证 URL 去重功能"""
    print("\n=== Bug #7: URL去重修复验证 ===")
    setup()

    test_url = "https://example.com/bug7-dedup-test"

    # 第一次创建 — 应为新记录
    rid1, is_new = WatchResultRepository.create_if_not_exists(
        source_id=1,
        keyword="bug7测试",
        request_url=test_url,
        response_status=200,
        response_size=100,
        result_data=json.dumps({"title": "测试1", "link": test_url}),
    )
    assert is_new, "第一次创建应为新记录"
    assert rid1 > 0
    print(f"  ✅ 第一次创建: ID={rid1}, is_new={is_new}")

    # 第二次相同URL — 应被去重
    rid2, is_new = WatchResultRepository.create_if_not_exists(
        source_id=1,
        keyword="bug7测试",
        request_url=test_url,
        response_status=200,
        response_size=100,
        result_data=json.dumps({"title": "测试2", "link": test_url}),
    )
    assert not is_new, f"相同URL应被去重，is_new={is_new}"
    assert rid2 == rid1, f"重复URL应返回已有记录ID={rid1}，实际={rid2}"
    print(f"  ✅ 重复URL被去重: 返回已有ID={rid2}, is_new={is_new}")

    # 不同URL — 应正常创建
    rid3, is_new = WatchResultRepository.create_if_not_exists(
        source_id=1,
        keyword="bug7测试",
        request_url="https://example.com/bug7-different",
        response_status=200,
        response_size=100,
        result_data=json.dumps({"title": "测试3"}),
    )
    assert is_new
    assert rid3 > 0 and rid3 != rid1
    print(f"  ✅ 不同URL正常创建: ID={rid3}")

    # 空URL — 不应被去重（空URL是合法的新采集）
    rid4, is_new = WatchResultRepository.create_if_not_exists(
        source_id=1,
        keyword="bug7测试",
        request_url="",
        response_status=0,
        response_size=0,
        result_data="empty",
    )
    # 空URL时 check_url_exists 返回 False，所以允许创建
    assert is_new, "空URL应允许创建"
    print(f"  ✅ 空URL允许创建: ID={rid4}")

    # 验证数据库记录数
    with get_db() as conn:
        cnt = conn.execute(
            "SELECT COUNT(*) as cnt FROM watch_results WHERE keyword LIKE ?",
            ("%bug7%",),
        ).fetchone()["cnt"]
    assert cnt == 3, f"应有3条记录，实际={cnt}"
    print(f"  ✅ 数据库中有{cnt}条记录（去重后）")

    setup()
    print("  ✅ Bug #7 修复验证通过")


def test_check_url_exists():
    """验证 URL 查重方法"""
    print("\n  --- 验证相关功能: URL查重 ---")
    setup()

    url = "https://example.com/bug7-check"

    # 不存在时
    exists = WatchResultRepository.check_url_exists(url)
    assert not exists
    print(f"  ✅ URL不存在: {exists}")

    # 创建后
    WatchResultRepository.create(1, "bug7", url, 200, 100, "{}")
    exists = WatchResultRepository.check_url_exists(url)
    assert exists
    print(f"  ✅ URL存在: {exists}")

    # 空URL
    exists = WatchResultRepository.check_url_exists("")
    assert not exists
    print(f"  ✅ 空URL: {exists}")

    setup()
    print("  ✅ URL查重正常")


if __name__ == "__main__":
    print("=" * 60)
    print("  Bug #7 修复验证")
    print("=" * 60)

    try:
        test_url_dedup()
        test_check_url_exists()
        print("\n" + "=" * 60)
        print("  ✅ Bug #7 全部验证通过！")
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
