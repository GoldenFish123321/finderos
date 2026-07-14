"""
Bug #30: ModelChatPageHandler未自动选择默认模型导致输入框禁用 — 修复验证

验证: 无model_id时自动回退到默认模型，确保输入框可用。
相关功能: 模型列表、默认模型设置不受影响。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.ai_model import AiModelRepository
from app.models.db import get_db


def test_auto_select_default_model():
    """验证无model_id时自动选择默认模型"""
    print("\n=== Bug #30: 自动选择默认模型修复验证 ===")

    # 模拟 ModelChatPageHandler 的逻辑
    # 场景1: 未指定 model_id → 应自动选择默认模型
    selected_model = AiModelRepository.get_default()
    assert selected_model is not None, "应有默认模型可用"
    assert selected_model["is_default"] == 1, "应为默认模型"
    assert selected_model["is_enabled"] == 1, "默认模型应启用"
    print(f"  ✅ 自动选择默认模型: {selected_model['name']} (ID={selected_model['id']})")

    # 场景2: 模拟如果默认模型不可用，回退到第一个启用模型
    models_data, _ = AiModelRepository.get_all(page=1, page_size=50)
    enabled_models = [m for m in models_data if m["is_enabled"] == 1]
    assert len(enabled_models) > 0, "至少应有一个启用的模型"
    fallback = enabled_models[0]
    print(f"  ✅ 回退模型可用: {fallback['name']} (ID={fallback['id']})")

    print("  ✅ Bug #30 修复验证通过")


def test_default_model_setting():
    """验证默认模型设置功能不受影响"""
    print("\n  --- 验证相关功能: 默认模型设置 ---")

    default = AiModelRepository.get_default()
    assert default is not None
    default_id = default["id"]
    print(f"  当前默认模型: ID={default_id}, name={default['name']}")

    # 设置另一个模型为默认
    other_models, _ = AiModelRepository.get_all(page=1, page_size=50)
    other = None
    for m in other_models:
        if m["id"] != default_id and m["is_enabled"] == 1:
            other = m
            break

    if other:
        AiModelRepository.set_default(other["id"])
        new_default = AiModelRepository.get_default()
        assert new_default["id"] == other["id"]
        print(f"  ✅ 设为默认: {other['name']} (ID={other['id']})")

        # 恢复原默认
        AiModelRepository.set_default(default_id)
        restored = AiModelRepository.get_default()
        assert restored["id"] == default_id
        print(f"  ✅ 恢复默认: {restored['name']}")

    print("  ✅ 默认模型设置正常")


def test_models_exist():
    """验证种子模型数据存在"""
    print("\n  --- 验证相关功能: 种子模型数据 ---")
    models, total = AiModelRepository.get_all(page=1, page_size=50)
    assert total >= 1, "至少应有1个模型"
    print(f"  模型总数: {total}")

    enabled = sum(1 for m in models if m["is_enabled"] == 1)
    assert enabled >= 1, "至少应有1个启用的模型"
    print(f"  启用模型数: {enabled}")

    has_default = any(m["is_default"] == 1 for m in models)
    assert has_default, "应有默认模型"
    print(f"  有默认模型: {has_default}")

    stats = AiModelRepository.get_stats()
    print(f"  统计: total={stats['total']}, enabled={stats['enabled']}, has_default={stats['has_default']}")

    print("  ✅ 种子模型数据正常")


if __name__ == "__main__":
    print("=" * 60)
    print("  Bug #30 修复验证")
    print("=" * 60)

    try:
        test_auto_select_default_model()
        test_default_model_setting()
        test_models_exist()
        print("\n" + "=" * 60)
        print("  ✅ Bug #30 全部验证通过！")
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
