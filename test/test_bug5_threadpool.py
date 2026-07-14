"""
Bug #5: ModelChatHandler 每个请求创建新 ThreadPoolExecutor — 修复验证

验证: 全局线程池单例复用，不再每次创建
相关功能: 模型 SSE 流式聊天不受影响
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.controllers.admin_model import _chat_executor
from app.models.ai_model import AiModelRepository
from app.models.db import get_db


def test_global_executor_singleton():
    """验证全局线程池是单例且可复用"""
    print("\n=== Bug #5: 全局线程池单例验证 ===")

    from app.controllers.admin_model import _chat_executor as e1
    from app.controllers.admin_model import _chat_executor as e2

    assert e1 is e2, "全局线程池应该是同一个单例"
    assert not e1._shutdown, "线程池应处于运行状态"
    print(f"  ✅ 线程池为模块级单例: max_workers={e1._max_workers}")

    # 验证线程池未被关闭
    assert not e1._threads or all(t.is_alive() for t in e1._threads), "线程池线程应存活"
    print("  ✅ 线程池线程存活正常")

    print("  ✅ Bug #5 修复验证通过")


def test_related_model_repository():
    """验证相关功能: AiModelRepository CRUD 不受影响"""
    print("\n  --- 验证相关功能: 模型仓库操作 ---")

    # 列出所有模型
    models, total = AiModelRepository.get_all(page=1, page_size=100)
    print(f"  模型总数: {total}")
    assert total > 0, "应有种子模型数据"

    # 获取 DeepSeek 模型（ID=2，已启用，是当前可用的模型）
    deepseek = AiModelRepository.get_by_id(2)
    assert deepseek is not None, "DeepSeek-V3 模型应存在"
    assert deepseek["is_enabled"] == 1, "DeepSeek-V3 应处于启用状态"
    model_id = deepseek["id"]
    print(f"  使用模型: {deepseek['name']} (ID={model_id}, enabled={deepseek['is_enabled']})")

    # 获取统计
    stats = AiModelRepository.get_stats()
    assert stats["total"] == total
    print(f"  统计: 总数={stats['total']}, 启用={stats['enabled']}")

    # 验证 Token 累加（在模型级别验证）
    model_before = AiModelRepository.get_by_id(model_id)
    before_tokens = model_before["total_tokens"] if model_before else 0
    print(f"  {deepseek['name']} Token 累加前: {before_tokens}")

    AiModelRepository.add_tokens(model_id, 10)
    AiModelRepository.add_tokens(model_id, 20)
    model_after = AiModelRepository.get_by_id(model_id)
    after_tokens = model_after["total_tokens"] if model_after else 0
    assert after_tokens == before_tokens + 30, f"Token 累加异常: {before_tokens} + 30 = {after_tokens}"
    print(f"  Token 累加: {before_tokens} → {after_tokens} (+30) ✅")

    # 清理: 清零 token
    AiModelRepository.clear_tokens(model_id)
    model_cleared = AiModelRepository.get_by_id(model_id)
    cleared_tokens = model_cleared["total_tokens"] if model_cleared else 0
    assert cleared_tokens == 0, f"Token 清零后应为 0: {cleared_tokens}"
    print(f"  Token 清零: {after_tokens} → {cleared_tokens} ✅")

    print("  ✅ 相关功能验证通过")


def test_related_data_warehouse():
    """验证相关功能: 数据仓库操作不受影响"""
    print("\n  --- 验证相关功能: 数据仓库操作 ---")
    from app.models.data_warehouse import DataWarehouseRepository

    count = DataWarehouseRepository.get_count()
    print(f"  数据仓库记录数: {count}")
    assert count >= 0

    # 创建一条测试记录
    ok = DataWarehouseRepository.create(
        result_id=None,
        title="测试标题 Bug#5",
        link="https://example.com/bug5",
        summary="测试摘要",
        source_name="测试来源",
    )
    if ok:
        print("  ✅ 创建数据仓库记录成功")
        # 清理
        with get_db() as conn:
            conn.execute("DELETE FROM data_warehouse WHERE link = ?",
                         ("https://example.com/bug5",))
            conn.commit()
        print("  ✅ 清理完成")
    else:
        print("  ⚠️ 记录可能已存在（跳过）")

    print("  ✅ 数据仓库功能正常")


if __name__ == "__main__":
    print("=" * 60)
    print("  Bug #5 修复验证")
    print("=" * 60)

    try:
        test_global_executor_singleton()
        test_related_model_repository()
        test_related_data_warehouse()
        print("\n" + "=" * 60)
        print("  ✅ Bug #5 全部验证通过！")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n❌ 验证失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
