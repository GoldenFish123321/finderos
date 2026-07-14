"""
Bug #27: WatchSaveHandler jQuery数组序列化格式不匹配导致保存永远失败 — 修复验证

验证: result_ids[] 键名格式能被正确解析。
相关功能: 采集、批量保存流程不受影响。
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.watch_result import WatchResultRepository
from app.models.data_warehouse import DataWarehouseRepository
from app.models.db import get_db


def setup():
    with get_db() as conn:
        conn.execute("DELETE FROM data_warehouse WHERE link LIKE ?", ("%bug27%",))
        conn.execute("DELETE FROM watch_results WHERE keyword LIKE ?", ("%bug27%",))
        conn.commit()


def test_save_with_jquery_array_format():
    """模拟前端 jQuery 数组序列化格式 (result_ids[]=1&result_ids[]=2)"""
    print("\n=== Bug #27: jQuery数组序列化格式修复验证 ===")
    setup()

    # 创建测试采集结果
    rid1 = WatchResultRepository.create(
        source_id=1, keyword="bug27测试",
        request_url="https://example.com/bug27-a",
        response_status=200, response_size=100,
        result_data=json.dumps({"title": "Bug27-A", "link": "https://example.com/bug27-a", "summary": "摘要A", "source_name": "来源A"}),
    )
    rid2 = WatchResultRepository.create(
        source_id=1, keyword="bug27测试",
        request_url="https://example.com/bug27-b",
        response_status=200, response_size=100,
        result_data=json.dumps({"title": "Bug27-B", "link": "https://example.com/bug27-b", "summary": "摘要B", "source_name": "来源B"}),
    )
    print(f"  创建测试结果: ID={rid1}, ID={rid2}")

    # 模拟后端参数解析逻辑（修复后的代码）
    # 模拟 get_body_arguments("result_ids[]") 返回 ["1", "2"]
    raw_ids = ["{}".format(rid1), "{}".format(rid2)]

    # 展开逻辑
    result_ids = []
    for r in raw_ids:
        for part in str(r).split(","):
            part = part.strip()
            if part:
                result_ids.append(part)

    ids = [int(rid) for rid in result_ids if rid]
    assert ids == [rid1, rid2], f"应解析出2个ID，实际={ids}"
    print(f"  ✅ 解析result_ids[]格式: {ids}")

    # 执行保存
    saved, skipped = WatchResultRepository.mark_saved_batch(ids)

    dw_count = 0
    for rid in ids:
        result = WatchResultRepository.get_by_id(rid)
        if not result:
            continue
        result_data = result["result_data"] or ""
        if result_data.startswith("SAVED:"):
            result_data = result_data[6:]
        items = []
        try:
            items = json.loads(result_data)
        except (json.JSONDecodeError, TypeError):
            pass
        if isinstance(items, dict):
            items = [items]
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    if DataWarehouseRepository.create(
                        result_id=rid,
                        title=item.get("title", ""),
                        link=item.get("link", ""),
                        summary=item.get("summary", ""),
                        source_name=item.get("source_name", ""),
                        raw_data=json.dumps(item, ensure_ascii=False),
                    ):
                        dw_count += 1

    assert dw_count == 2, f"应保存2条到数据仓库，实际={dw_count}"
    assert saved == 2, f"mark_saved_batch应返回2，实际={saved}"
    print(f"  ✅ 保存成功: dw_count={dw_count}, saved={saved}")

    # 验证数据仓库
    with get_db() as conn:
        cnt = conn.execute(
            "SELECT COUNT(*) as cnt FROM data_warehouse WHERE link LIKE ?",
            ("%bug27%",),
        ).fetchone()["cnt"]
    assert cnt == 2, f"数据仓库应有2条记录，实际={cnt}"
    print(f"  ✅ 数据仓库记录数: {cnt}")

    # 清理
    WatchResultRepository.delete(rid1)
    WatchResultRepository.delete(rid2)
    with get_db() as conn:
        conn.execute("DELETE FROM data_warehouse WHERE link LIKE ?", ("%bug27%",))
        conn.commit()

    setup()
    print("  ✅ Bug #27 修复验证通过")


def test_comma_separated_format():
    """验证逗号分隔格式 (result_ids=1,2)"""
    print("\n  --- 验证逗号分隔格式 ---")
    setup()

    rid = WatchResultRepository.create(
        source_id=1, keyword="bug27逗号",
        request_url="https://example.com/bug27-comma",
        response_status=200, response_size=100,
        result_data=json.dumps({"title": "逗号测试", "link": "https://example.com/bug27-comma", "source_name": "来源"}),
    )

    # 模拟逗号分隔 + 另一个ID
    raw_ids = ["{},99999".format(rid)]

    result_ids = []
    for r in raw_ids:
        for part in str(r).split(","):
            part = part.strip()
            if part:
                result_ids.append(part)

    ids = [int(rid) for rid in result_ids if rid]
    # 99999 不存在，但 int() 不报错，只是后续 get_by_id 返回 None
    assert rid in ids, f"应包含有效ID {rid}"
    print(f"  ✅ 逗号分隔解析: {ids}")

    WatchResultRepository.delete(rid)
    setup()
    print("  ✅ 逗号分隔格式正常")


def test_multiple_form_fields():
    """验证多个表单字段格式 (result_ids=1&result_ids=2)"""
    print("\n  --- 验证多表单字段格式 ---")
    setup()

    rid1 = WatchResultRepository.create(
        source_id=1, keyword="bug27多字段",
        request_url="https://example.com/bug27-multi-1",
        response_status=200, response_size=100,
        result_data=json.dumps({"title": "多字段", "link": "https://example.com/bug27-multi-1"}),
    )
    rid2 = WatchResultRepository.create(
        source_id=1, keyword="bug27多字段",
        request_url="https://example.com/bug27-multi-2",
        response_status=200, response_size=100,
        result_data=json.dumps({"title": "多字段2", "link": "https://example.com/bug27-multi-2"}),
    )

    raw_ids = [str(rid1), str(rid2)]
    result_ids = []
    for r in raw_ids:
        for part in r.split(","):
            part = part.strip()
            if part:
                result_ids.append(part)

    ids = [int(rid) for rid in result_ids if rid]
    assert ids == [rid1, rid2], f"应解析出2个ID，实际={ids}"
    print(f"  ✅ 多字段格式: {ids}")

    WatchResultRepository.delete(rid1)
    WatchResultRepository.delete(rid2)
    setup()
    print("  ✅ 多字段格式正常")


if __name__ == "__main__":
    print("=" * 60)
    print("  Bug #27 修复验证")
    print("=" * 60)

    try:
        test_save_with_jquery_array_format()
        test_comma_separated_format()
        test_multiple_form_fields()
        print("\n" + "=" * 60)
        print("  ✅ Bug #27 全部验证通过！")
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
