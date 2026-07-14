"""
Bug #6: AiModelRepository 无法清除 API Key — 修复验证

验证: update() 传空字符串会清空数据库中已有的 API Key
相关功能: 模型创建/查询/更新不受影响
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.ai_model import AiModelRepository
from app.models.db import get_db


def test_api_key_clear():
    """验证 API Key 可以被清除（传空字符串）"""
    print("\n=== Bug #6: API Key 清除修复验证 ===")

    # 使用 DeepSeek 模型（ID=2）做测试
    model_id = 2
    model_before = AiModelRepository.get_by_id(model_id)
    assert model_before is not None, "模型应存在"

    # 记录当前的 API Key
    old_key = model_before["api_key"] or ""
    print(f"  DeepSeek-V3 当前 API Key: {'已设置' if old_key else '未设置'}")

    # 先设一个测试 key
    AiModelRepository.update(
        model_id, model_before["name"], model_before["provider"],
        model_before["api_base"], "test_key_123", model_before["model_name"]
    )
    model_with_key = AiModelRepository.get_by_id(model_id)
    assert model_with_key["api_key"] == "test_key_123", \
        f"设置 API Key 失败: {model_with_key['api_key']}"
    print("  ✅ 设置 API Key = 'test_key_123' 成功")

    # 核心验证：传空字符串清除 API Key
    ok = AiModelRepository.update(
        model_id, model_before["name"], model_before["provider"],
        model_before["api_base"], "", model_before["model_name"]
    )
    assert ok, "更新应成功"
    model_cleared = AiModelRepository.get_by_id(model_id)
    assert model_cleared["api_key"] == "", \
        f"❌ Bug #6 未修复: 传空字符串后 API Key 仍为 '{model_cleared['api_key']}'"
    print("  ✅ 传空字符串成功清除 API Key: '' ")

    # 恢复原有 key
    AiModelRepository.update(
        model_id, model_before["name"], model_before["provider"],
        model_before["api_base"], old_key, model_before["model_name"]
    )
    model_restored = AiModelRepository.get_by_id(model_id)
    assert model_restored["api_key"] == old_key, \
        f"恢复 API Key 失败: {model_restored['api_key']}"
    print(f"  ✅ 恢复 API Key: {'已设置' if old_key else '未设置'}")

    print("  ✅ Bug #6 修复验证通过")


def test_related_model_crud():
    """验证相关功能: 模型 CRUD 不受影响"""
    print("\n  --- 验证相关功能: 模型 CRUD ---")

    # 查询所有模型
    models, total = AiModelRepository.get_all(page=1, page_size=100)
    print(f"  模型总数: {total}")

    # 创建新模型
    new_id = AiModelRepository.create(
        name="测试模型-Bug6",
        provider="openai",
        api_base="https://api.openai.com/v1",
        api_key="sk-test",
        model_name="gpt-test",
        category="text",
        temperature=0.7,
        top_p=1.0,
        top_k=50,
        max_tokens=4096,
        context_size=8192,
    )
    assert new_id > 0, f"创建模型失败: new_id={new_id}"
    print(f"  ✅ 创建模型成功: ID={new_id}")

    # 查询
    model = AiModelRepository.get_by_id(new_id)
    assert model is not None
    assert model["name"] == "测试模型-Bug6"
    print(f"  ✅ 查询模型成功: {model['name']}")

    # 更新
    ok = AiModelRepository.update(
        new_id, "测试模型-Bug6-已更新", model["provider"],
        model["api_base"], "sk-updated", model["model_name"]
    )
    assert ok
    model = AiModelRepository.get_by_id(new_id)
    assert model["name"] == "测试模型-Bug6-已更新"
    assert model["api_key"] == "sk-updated"
    print(f"  ✅ 更新模型成功: 名称={model['name']}, API Key 正常")

    # 删除
    ok = AiModelRepository.delete(new_id)
    assert ok
    model = AiModelRepository.get_by_id(new_id)
    assert model is None
    print(f"  ✅ 删除模型成功")

    # Token 统计
    stats = AiModelRepository.get_stats()
    assert "total" in stats
    assert "enabled" in stats
    print(f"  ✅ 模型统计正常: {stats}")

    print("  ✅ 相关功能验证通过")


if __name__ == "__main__":
    print("=" * 60)
    print("  Bug #6 修复验证")
    print("=" * 60)

    try:
        test_api_key_clear()
        test_related_model_crud()
        print("\n" + "=" * 60)
        print("  ✅ Bug #6 全部验证通过！")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n❌ 验证失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
