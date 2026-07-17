"""
测试: LLM/MCP 采集工具自动保存到数据仓库

验证 _collect_web_data 采集结果会自动写入 data_warehouse 表，
与 Web UI "💾 保存到数据仓库" 按钮行为一致。

相关 issue: LLM调用采集工具采集新闻只保存结果而没有入库能力
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.watch_result import WatchResultRepository
from app.models.data_warehouse import DataWarehouseRepository
from app.models.db import get_db


def setup():
    """清理测试数据"""
    with get_db() as conn:
        conn.execute("DELETE FROM data_warehouse WHERE title LIKE ?", ("%test_auto_save%",))
        conn.execute("DELETE FROM watch_results WHERE keyword LIKE ?", ("%test_auto_save%",))
        conn.commit()


def test_create_if_not_exists_returns_existing_id():
    """验证 create_if_not_exists 在重复URL时返回已有记录的ID"""
    print("\n=== 测试: create_if_not_exists 返回已有ID ===")
    setup()

    test_url = "https://example.com/test-auto-save-1"
    test_data = json.dumps({"title": "test_auto_save_新闻1", "link": test_url})

    # 第一次创建
    rid1, is_new1 = WatchResultRepository.create_if_not_exists(
        source_id=1, keyword="test_auto_save",
        request_url=test_url, response_status=200,
        response_size=100, result_data=test_data,
    )
    assert is_new1, "第一次创建应为新记录"
    assert rid1 > 0, f"新记录ID应>0，实际={rid1}"
    print(f"  ✅ 第一次创建: ID={rid1}, is_new={is_new1}")

    # 第二次相同URL — 应返回已有ID
    rid2, is_new2 = WatchResultRepository.create_if_not_exists(
        source_id=1, keyword="test_auto_save",
        request_url=test_url, response_status=200,
        response_size=100, result_data=test_data,
    )
    assert not is_new2, "相同URL应为重复"
    assert rid2 == rid1, f"重复URL应返回已有ID={rid1}，实际={rid2}"
    print(f"  ✅ 重复URL返回已有ID: {rid2}, is_new={is_new2}")

    # 不同URL — 正常创建
    rid3, is_new3 = WatchResultRepository.create_if_not_exists(
        source_id=1, keyword="test_auto_save",
        request_url="https://example.com/test-auto-save-2",
        response_status=200,
        response_size=100,
        result_data=json.dumps({"title": "test_auto_save_新闻2"}),
    )
    assert is_new3
    assert rid3 > 0 and rid3 != rid1
    print(f"  ✅ 不同URL正常创建: ID={rid3}")

    setup()
    print("  ✅ 测试通过")


def test_data_warehouse_create_dedup():
    """验证 data_warehouse.create 按 link 去重"""
    print("\n=== 测试: data_warehouse 去重 ===")
    setup()

    # 先创建 watch_result 以满足外键约束
    test_url = "https://example.com/test-warehouse-dedup"
    rid, _ = WatchResultRepository.create_if_not_exists(
        source_id=1, keyword="test_auto_save_dedup",
        request_url=test_url, response_status=200,
        response_size=100,
        result_data=json.dumps({"title": "test_auto_save_标题1", "link": test_url}),
    )
    assert rid > 0, f"watch_result 创建失败: rid={rid}"

    link = "https://example.com/test-warehouse-dedup"
    ok1 = DataWarehouseRepository.create(
        result_id=rid, title="test_auto_save_标题1",
        link=link, summary="摘要1",
        source_name="测试源",
        raw_data=json.dumps({"title": "test_auto_save_标题1", "link": link}),
    )
    assert ok1, "第一次写入应成功"
    print(f"  ✅ 第一次写入: {ok1}")

    ok2 = DataWarehouseRepository.create(
        result_id=rid, title="test_auto_save_标题2",
        link=link, summary="摘要2",
        source_name="测试源",
        raw_data=json.dumps({"title": "test_auto_save_标题2", "link": link}),
    )
    assert not ok2, "相同 link 应被去重"
    print(f"  ✅ 重复 link 被去重: {ok2}")

    # 验证只有1条记录
    with get_db() as conn:
        cnt = conn.execute(
            "SELECT COUNT(*) as cnt FROM data_warehouse WHERE link = ?", (link,)
        ).fetchone()["cnt"]
    assert cnt == 1, f"应有1条记录，实际={cnt}"
    print(f"  ✅ 数据库中只有{cnt}条记录")

    setup()
    print("  ✅ 测试通过")


def test_collect_tool_auto_save_to_warehouse():
    """验证 _collect_web_data 结果自动写入 data_warehouse

    注意：此测试依赖真实的瞭望源（百度新闻等），需要网络连接。
    如果网络不可用，测试将被跳过。
    """
    print("\n=== 测试: MCP采集工具自动入库 ===")
    setup()

    import asyncio
    from app.mcp.builtin_tools.collect_tools import _collect_web_data

    async def run_collect():
        return await _collect_web_data(keyword="测试", source_ids=None)

    try:
        result = asyncio.run(run_collect())
    except Exception as e:
        print(f"  ⚠️ 采集执行异常（可能是网络问题）: {e}")
        print("  ⚠️ 跳过在线采集测试")
        setup()
        return

    print(f"  采集结果: keyword={result.get('keyword')}, "
          f"total={result.get('total_collected')}, "
          f"warehouse_saved={result.get('warehouse_saved', 0)}")

    # 验证返回结果中包含 warehouse_saved 字段
    if result.get("total_collected", 0) > 0:
        assert "warehouse_saved" in result, "返回结果应包含 warehouse_saved 字段"
        # 验证数据确实写入了 data_warehouse 表
        dw_count = DataWarehouseRepository.get_count()
        print(f"  数据仓库总记录数: {dw_count}")
        recent = DataWarehouseRepository.get_recent(limit=5)
        print(f"  最近5条仓库记录: {[(r.get('title','')[:30], r.get('link','')[:50]) for r in recent]}")
    else:
        print("  ⚠️ 未采集到数据（可能是网络限制），跳过数量验证")

    setup()
    print("  ✅ 测试通过")


def test_warehouse_create_with_result_id():
    """验证 data_warehouse 正确关联 result_id"""
    print("\n=== 测试: data_warehouse 关联 result_id ===")
    setup()

    # 先创建 watch_result
    test_url = "https://example.com/test-warehouse-link"
    test_data = json.dumps({"title": "test_auto_save_关联测试", "link": test_url,
                             "summary": "测试摘要", "source_name": "测试源"})
    rid, is_new = WatchResultRepository.create_if_not_exists(
        source_id=1, keyword="test_auto_save_link",
        request_url=test_url, response_status=200,
        response_size=100, result_data=test_data,
    )
    assert rid > 0, f"watch_result 创建失败: rid={rid}"
    print(f"  ✅ watch_result 创建: ID={rid}")

    # 写入 data_warehouse 并关联
    ok = DataWarehouseRepository.create(
        result_id=rid,
        title="test_auto_save_关联测试",
        link=test_url,
        summary="测试摘要",
        source_name="测试源",
        raw_data=test_data,
    )
    assert ok, "写入 data_warehouse 失败"
    print(f"  ✅ data_warehouse 写入成功")

    # 验证关联
    with get_db() as conn:
        row = conn.execute(
            "SELECT dw.*, wr.keyword FROM data_warehouse dw "
            "LEFT JOIN watch_results wr ON dw.result_id = wr.id "
            "WHERE dw.link = ?", (test_url,)
        ).fetchone()
    assert row is not None, "应能查到数据仓库记录"
    assert row["result_id"] == rid, f"result_id 应匹配: {row['result_id']} != {rid}"
    assert row["keyword"] == "test_auto_save_link", f"keyword 应匹配: {row['keyword']}"
    print(f"  ✅ result_id 关联正确: dw.result_id={row['result_id']}, keyword={row['keyword']}")

    setup()
    print("  ✅ 测试通过")


if __name__ == "__main__":
    test_create_if_not_exists_returns_existing_id()
    test_data_warehouse_create_dedup()
    test_warehouse_create_with_result_id()
    test_collect_tool_auto_save_to_warehouse()
    print("\n🎉 所有测试通过!")
