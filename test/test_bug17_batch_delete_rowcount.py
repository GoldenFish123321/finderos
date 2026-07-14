"""
Bug #17: DataWarehouseRepository.batch_delete total_changes 计数错误 — 修复验证

验证: batch_delete 使用 cursor.rowcount 精确判断，不再虚高计数。
相关功能: 单条删除、批量创建不受影响。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.data_warehouse import DataWarehouseRepository
from app.models.db import get_db


def setup():
    """清理测试数据"""
    with get_db() as conn:
        conn.execute("DELETE FROM data_warehouse WHERE link LIKE ?", ("%bug17%",))
        conn.execute("DELETE FROM data_warehouse WHERE link LIKE ?", ("%bug17-nonexist%",))
        conn.commit()


def test_batch_delete_accurate_count():
    """验证 batch_delete 计数精确（Bug #17 核心验证）"""
    print("\n=== Bug #17: batch_delete total_changes 计数修复验证 ===")
    setup()

    # 创建3条记录
    ids = []
    for i in range(3):
        ok = DataWarehouseRepository.create(
            result_id=None,
            title=f"Bug17测试-{i}",
            link=f"https://example.com/bug17-{i}",
            summary=f"测试摘要{i}",
            source_name="测试来源",
        )
        print(f"  创建记录{i}: {'成功' if ok else '失败'}")

    # 获取创建的记录ID
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id FROM data_warehouse WHERE link LIKE ?",
            ("%bug17%",),
        ).fetchall()
        ids = [r["id"] for r in rows]
    print(f"  已创建 {len(ids)} 条记录: {ids}")

    assert len(ids) >= 3, f"应至少有3条记录，实际{len(ids)}"

    # 删除第1条
    count = DataWarehouseRepository.batch_delete([ids[0]])
    assert count == 1, f"删除1条应返回1，实际={count}"
    print(f"  ✅ 删除1条: 返回 {count}")

    # 用不存在的ID + 一个存在的ID 混合删除
    count = DataWarehouseRepository.batch_delete([99999, ids[1], 99998])
    assert count == 1, f"混合删除(1存在+2不存在)应返回1，实际={count}"
    print(f"  ✅ 混合删除(1存在+2不存在): 返回 {count} ✓")

    # 全不存在的ID
    count = DataWarehouseRepository.batch_delete([99997, 99996])
    assert count == 0, f"删除不存在的ID应返回0，实际={count}"
    print(f"  ✅ 删除不存在的ID: 返回 {count} ✓")

    # 删除剩余的
    remaining = [r for r in ids if r != ids[0] and r != ids[1]]
    if remaining:
        count = DataWarehouseRepository.batch_delete(remaining)
        print(f"  ✅ 删除剩余{len(remaining)}条: 返回 {count}")

    # 验证全部已删除
    with get_db() as conn:
        cnt = conn.execute(
            "SELECT COUNT(*) as cnt FROM data_warehouse WHERE link LIKE ?",
            ("%bug17%",),
        ).fetchone()["cnt"]
    assert cnt == 0, f"应全部删除，实际剩余{cnt}条"
    print(f"  ✅ 验证全部删除: 剩余 {cnt} 条")

    setup()
    print("  ✅ Bug #17 修复验证通过")


def test_single_delete_rowcount():
    """验证单条删除也使用 rowcount"""
    print("\n  --- 验证相关功能: 单条删除 ---")
    setup()

    ok = DataWarehouseRepository.create(
        result_id=None,
        title="Bug17单条测试",
        link="https://example.com/bug17-single",
        summary="单条测试",
        source_name="测试",
    )
    assert ok

    with get_db() as conn:
        row = conn.execute(
            "SELECT id FROM data_warehouse WHERE link = ?",
            ("https://example.com/bug17-single",),
        ).fetchone()
        dw_id = row["id"]

    # 删除存在的记录
    ok = DataWarehouseRepository.delete(dw_id)
    assert ok, "删除存在的记录应返回True"
    print(f"  ✅ 删除存在记录: True")

    # 删除不存在的记录
    ok = DataWarehouseRepository.delete(dw_id)
    assert not ok, "删除不存在的记录应返回False"
    print(f"  ✅ 删除不存在记录: False")

    setup()
    print("  ✅ 单条删除验证通过")


def test_batch_create_unaffected():
    """验证 batch_create 的 total_changes 差值用法不受影响"""
    print("\n  --- 验证相关功能: 批量创建 ---")
    setup()

    items = [
        {"title": "批量1", "link": "https://example.com/bug17-batch-1", "summary": "s1", "source_name": "src"},
        {"title": "批量2", "link": "https://example.com/bug17-batch-2", "summary": "s2", "source_name": "src"},
        {"title": "批量3", "link": "https://example.com/bug17-batch-3", "summary": "s3", "source_name": "src"},
    ]
    count = DataWarehouseRepository.batch_create(items)
    assert count == 3, f"批量创建3条应返回3，实际={count}"
    print(f"  ✅ 批量创建3条: {count}")

    # 重复创建应被去重（link去重）
    count = DataWarehouseRepository.batch_create(items)
    assert count == 0, f"重复批量创建应返回0，实际={count}"
    print(f"  ✅ 重复批量创建(去重): {count}")

    setup()
    print("  ✅ 批量创建不受影响")


if __name__ == "__main__":
    print("=" * 60)
    print("  Bug #17 修复验证")
    print("=" * 60)

    try:
        test_batch_delete_accurate_count()
        test_single_delete_rowcount()
        test_batch_create_unaffected()
        print("\n" + "=" * 60)
        print("  ✅ Bug #17 全部验证通过！")
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
