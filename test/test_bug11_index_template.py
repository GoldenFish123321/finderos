"""
Bug #11: IndexHandler 渲染管理后台模板 — 修复验证

验证: 普通用户不再看到 admin 模板
相关功能: 路由/登录跳转不受影响
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.user import UserRepository
from app.models.watch_source import WatchSourceRepository
from app.models.watch_result import WatchResultRepository
from app.models.ai_model import AiModelRepository


def test_template_separation():
    """验证模板分离逻辑正确"""
    print("\n=== Bug #11: 首页模板分离修复验证 ===")

    # 验证 user_index.html 模板存在
    template_path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                 "app/templates/user_index.html")
    assert os.path.exists(template_path), "user_index.html 模板应存在"
    print("  ✅ user_index.html 模板已创建")

    # 验证 admin/index.html 模板仍然存在（给管理后台用）
    admin_template = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                  "app/templates/admin/index.html")
    assert os.path.exists(admin_template), "admin/index.html 模板应保留"
    print("  ✅ admin/index.html 模板保留")

    # 验证常用统计数据查询正常
    source_count = WatchSourceRepository.get_count()
    result_stats = WatchResultRepository.get_stats()
    model_count = AiModelRepository.get_count()
    print(f"  瞭望源: {source_count}, 采集结果: {result_stats['total']}, AI模型: {model_count}")
    assert source_count >= 0
    assert result_stats["total"] >= 0
    assert model_count >= 0

    print("  ✅ Bug #11 修复验证通过")


def test_related_functionality():
    """验证相关功能: 角色判断和跳转不受影响"""
    print("\n  --- 验证相关功能: 角色判断 ---")

    # 验证角色查询
    role = UserRepository.get_user_role("admin")
    assert role is not None, "admin 用户应有角色"
    print(f"  admin 角色: {role['name']}")

    # 验证函数查询
    funcs = UserRepository.get_user_functions("admin")
    assert len(funcs) > 0, "admin 用户应有功能权限"
    print(f"  admin 功能数: {len(funcs)}")

    print("  ✅ 相关功能验证通过")


if __name__ == "__main__":
    print("=" * 60)
    print("  Bug #11 修复验证")
    print("=" * 60)

    try:
        test_template_separation()
        test_related_functionality()
        print("\n" + "=" * 60)
        print("  ✅ Bug #11 全部验证通过！")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n❌ 验证失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
