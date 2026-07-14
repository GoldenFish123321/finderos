"""
Bug #28: DataWarehouseRepository.get_by_id/get_all 查询缺少模板所需列导致500 — 修复验证

验证: request_url、response_status、response_size、result_data 列存在于查询结果中。
相关功能: 数据仓库列表、详情页不受影响。
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.data_warehouse import DataWarehouseRepository
from app.models.watch_result import WatchResultRepository
from app.models.db import get_db


def setup():
    with get_db() as conn:
        conn.execute("DELETE FROM data_warehouse WHERE link LIKE ?", ("%bug28%",))
        conn.execute("DELETE FROM watch_results WHERE keyword LIKE ?", ("%bug28%",))
        conn.commit()


def test_detail_columns_present():
    """验证详情查询返回模板所需的所有列（Bug #28 核心）"""
    print("\n=== Bug #28: get_by_id 缺少模板列修复验证 ===")
    setup()

    # 创建测试数据
    rid = WatchResultRepository.create(
        source_id=1,
        keyword="bug28关键词",
        request_url="https://example.com/bug28-url",
        response_status=200,
        response_size=2048,
        result_data=json.dumps({"title": "Bug28标题", "link": "https://example.com/bug28"}),
    )
    print(f"  创建 watch_result ID={rid}")

    # 保存到数据仓库
    ok = DataWarehouseRepository.create(
        result_id=rid,
        title="Bug28标题",
        link="https://example.com/bug28",
        summary="测试摘要",
        source_name="测试来源",
        raw_data=json.dumps({"title": "Bug28标题"}),
    )
    assert ok
    print(f"  保存到数据仓库成功")

    # 获取数据仓库记录ID
    with get_db() as conn:
        dw_row = conn.execute(
            "SELECT id FROM data_warehouse WHERE link = ?",
            ("https://example.com/bug28",),
        ).fetchone()
    dw_id = dw_row["id"]
    print(f"  数据仓库记录 ID={dw_id}")

    # 测试 get_by_id 返回的列
    result = DataWarehouseRepository.get_by_id(dw_id)
    assert result is not None, "get_by_id 应返回记录"

    # 验证模板所需的所有列都存在（模拟 warehouse_detail.html 的引用）
    required_columns = [
        "id",           # result['id']
        "source_name",  # result['source_name']
        "keyword",      # result['keyword']
        "request_url",  # result['request_url']  ← 之前缺失！
        "response_status",  # result['response_status']  ← 之前缺失！
        "response_size",    # result['response_size']  ← 之前缺失！
        "result_data",      # result['result_data']  ← 之前缺失！
        "created_at",       # result['created_at']
    ]
    for col in required_columns:
        try:
            val = result[col]
            print(f"  ✅ result['{col}'] = {str(val)[:50]}...")
        except KeyError:
            print(f"  ❌ BUG仍存在: result['{col}'] 列缺失!")
            assert False, f"Bug #28 未修复: 列 '{col}' 缺失"

    print("  ✅ Bug #28 修复验证通过")

    # 清理
    WatchResultRepository.delete(rid)
    with get_db() as conn:
        conn.execute("DELETE FROM data_warehouse WHERE link = ?",
                     ("https://example.com/bug28",))
        conn.commit()
    setup()


def test_list_columns_present():
    """验证列表查询也返回所需列"""
    print("\n  --- 验证 get_all 列 ---")
    setup()

    rid = WatchResultRepository.create(
        source_id=1, keyword="bug28列表",
        request_url="https://example.com/bug28-list",
        response_status=200, response_size=512,
        result_data='{}',
    )
    DataWarehouseRepository.create(
        result_id=rid, title="列表测试",
        link="https://example.com/bug28-list",
        summary="", source_name="来源",
    )

    rows, total = DataWarehouseRepository.get_all(page=1, page_size=10, keyword="列表测试")
    assert total >= 1
    row = None
    for r in rows:
        if r["link"] == "https://example.com/bug28-list":
            row = r
            break
    assert row is not None

    # 验证列表模板所需的列
    list_columns = ["id", "title", "source_name", "keyword", "response_status", "response_size", "created_at"]
    for col in list_columns:
        try:
            _ = row[col]
        except KeyError:
            assert False, f"列表查询缺少列: {col}"
    print(f"  ✅ get_all 返回所有列表模板所需列")

    WatchResultRepository.delete(rid)
    with get_db() as conn:
        conn.execute("DELETE FROM data_warehouse WHERE link = ?",
                     ("https://example.com/bug28-list",))
        conn.commit()
    setup()
    print("  ✅ 列表查询列完整")


def test_warehouse_crud_unaffected():
    """验证数据仓库 CRUD 不受影响"""
    print("\n  --- 验证数据仓库 CRUD ---")

    rid = WatchResultRepository.create(1, "bug28crud", "https://e.com/bug28", 200, 100, "{}")
    ok = DataWarehouseRepository.create(rid, "CRUD测试", "https://e.com/bug28", "", "src")
    assert ok
    print(f"  ✅ 创建成功")

    with get_db() as conn:
        dw = conn.execute("SELECT id FROM data_warehouse WHERE link=?", ("https://e.com/bug28",)).fetchone()

    result = DataWarehouseRepository.get_by_id(dw["id"])
    assert result is not None
    assert result["title"] == "CRUD测试"
    print(f"  ✅ 查询成功: {result['title']}")

    ok = DataWarehouseRepository.delete(dw["id"])
    assert ok
    assert DataWarehouseRepository.get_by_id(dw["id"]) is None
    print(f"  ✅ 删除成功")

    WatchResultRepository.delete(rid)
    with get_db() as conn:
        conn.execute("DELETE FROM data_warehouse WHERE link=?", ("https://e.com/bug28",))
        conn.commit()
    print("  ✅ CRUD 正常")


if __name__ == "__main__":
    print("=" * 60)
    print("  Bug #28 修复验证")
    print("=" * 60)

    try:
        test_detail_columns_present()
        test_list_columns_present()
        test_warehouse_crud_unaffected()
        print("\n" + "=" * 60)
        print("  ✅ Bug #28 全部验证通过！")
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
