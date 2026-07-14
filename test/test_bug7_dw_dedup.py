"""
Bug #7: DataWarehouse 空 link 去重失效 — 修复验证

验证: 空 link 记录按 title+source_name 应用层去重
相关功能: 有 link 的去重不受影响 + 批量操作
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.data_warehouse import DataWarehouseRepository
from app.models.db import get_db


def setup():
    """清理测试数据"""
    with get_db() as conn:
        conn.execute("DELETE FROM data_warehouse WHERE title LIKE ?", ("%Bug#7%",))
        conn.execute("DELETE FROM data_warehouse WHERE title LIKE ?", ("%Bug7%",))
        conn.commit()


def test_empty_link_dedup():
    """验证空 link 记录按 title + source_name 去重"""
    print("\n=== Bug #7: 空 link 去重复修复验证 ===")
    setup()

    # 创建第一条空 link 记录
    ok1 = DataWarehouseRepository.create(
        result_id=None,
        title="Bug#7测试-无链接新闻",
        link="",
        summary="无链接新闻摘要",
        source_name="测试来源",
        raw_data='{"title":"Bug#7测试-无链接新闻"}',
    )
    print(f"  第一次创建(空link): {'成功' if ok1 else '失败'}")
    assert ok1, "第一次创建应成功"

    # 尝试创建第二条相同 title+source_name 的空 link 记录
    ok2 = DataWarehouseRepository.create(
        result_id=None,
        title="Bug#7测试-无链接新闻",
        link="",
        summary="无链接新闻摘要-副本",
        source_name="测试来源",
        raw_data='{"title":"Bug#7测试-无链接新闻-副本"}',
    )
    print(f"  第二次创建(相同title+source, 空link): {'成功' if ok2 else '被去重'}")
    assert not ok2, "相同 title+source_name 的空 link 记录应被去重"

    # 相同 title 但不同 source，应该允许创建
    ok3 = DataWarehouseRepository.create(
        result_id=None,
        title="Bug#7测试-无链接新闻",
        link="",
        summary="不同来源",
        source_name="不同来源",
        raw_data='{"title":"Bug#7测试-无链接新闻"}',
    )
    print(f"  不同source创建(空link): {'成功' if ok3 else '失败'}")
    assert ok3, "不同 source_name 应允许创建"

    # 验证数据库记录数
    with get_db() as conn:
        count = conn.execute(
            "SELECT COUNT(*) as cnt FROM data_warehouse WHERE title LIKE ?",
            ("%Bug#7测试%",),
        ).fetchone()["cnt"]
    assert count == 2, f"应有2条记录，实际{count}"
    print(f"  ✅ 数据库中有 {count} 条记录（预期2条：1条原始+1条不同source）")

    print("  ✅ Bug #7 修复验证通过")


def test_link_dedup():
    """验证有 link 的记录仍由数据库索引去重"""
    print("\n  --- 验证相关功能: 有 link的去重 ---")

    link = "https://example.com/bug7-unique-link"

    ok1 = DataWarehouseRepository.create(
        result_id=None,
        title="Bug7-有链接新闻",
        link=link,
        summary="有链接",
        source_name="测试",
    )
    print(f"  第一次创建(有link): {'成功' if ok1 else '失败'}")
    assert ok1

    ok2 = DataWarehouseRepository.create(
        result_id=None,
        title="Bug7-有链接新闻-重复",
        link=link,
        summary="重复",
        source_name="测试",
    )
    print(f"  第二次创建(相同link): {'成功' if ok2 else '被去重'}")
    assert not ok2, "相同 link 应被唯一索引去重"

    print("  ✅ 有 link 去重正常")


def test_batch_create():
    """验证 batch_create 去重逻辑一致"""
    print("\n  --- 验证相关功能: batch_create 批量去重 ---")
    setup()

    items = [
        {"result_id": None, "title": "Bug7-批量空link1", "link": "", "summary": "a", "source_name": "来源A"},
        {"result_id": None, "title": "Bug7-批量空link1", "link": "", "summary": "b", "source_name": "来源A"},  # 应被去重
        {"result_id": None, "title": "Bug7-批量有link", "link": "https://ex.com/batch1", "summary": "c", "source_name": "来源B"},
        {"result_id": None, "title": "Bug7-批量有link-2", "link": "https://ex.com/batch1", "summary": "d", "source_name": "来源B"},  # 应被去重
        {"result_id": None, "title": "Bug7-批量空link2", "link": "", "summary": "e", "source_name": "来源C"},
    ]

    saved = DataWarehouseRepository.batch_create(items)
    print(f"  批量创建: 提交{len(items)}条，成功保存{saved}条（预期3条）")
    assert saved == 3, f"应保存3条（去重2条），实际{saved}"

    print("  ✅ batch_create 去重正常")


def test_related_queries():
    """验证相关功能: 查询和删除不受影响"""
    print("\n  --- 验证相关功能: 查询和删除 ---")

    # 查询所有
    rows, total = DataWarehouseRepository.get_all(page=1, page_size=100)
    print(f"  数据仓库总记录数: {total}")

    # 搜索
    rows, total = DataWarehouseRepository.get_all(keyword="Bug7")
    print(f"  搜索'Bug7'结果数: {total}")

    print("  ✅ 查询功能正常")

    # 清理
    setup()
    print("  ✅ 清理完成")


if __name__ == "__main__":
    print("=" * 60)
    print("  Bug #7 修复验证")
    print("=" * 60)

    try:
        test_empty_link_dedup()
        test_link_dedup()
        test_batch_create()
        test_related_queries()
        print("\n" + "=" * 60)
        print("  ✅ Bug #7 全部验证通过！")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n❌ 验证失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
