"""
模型分组隔离测试。

覆盖：
- 管理员提供模型（admin 组）与用户自助模型（user 组）分开查询
- 用户只能访问自己的 user 组模型，不能访问其他用户模型
- 每个用户自己的默认模型不影响管理员默认模型
- Chat/快速配置模板包含分组展示与“我的模型配置”管理入口
"""
from pathlib import Path


def test_admin_and_user_models_are_grouped_and_isolated():
    from app.models.ai_model import AiModelRepository

    admin_default = AiModelRepository.get_default()
    assert admin_default is not None
    assert admin_default.get("model_scope") == "admin"
    assert admin_default.get("owner_username", "") == ""

    alice_model_id = AiModelRepository.create(
        name="Alice Private Model",
        provider="openai",
        api_base="https://api.alice.example/v1",
        api_key="sk-alice",
        model_name="alice-model",
        category="text",
        model_scope="user",
        owner_username="alice",
    )
    bob_model_id = AiModelRepository.create(
        name="Bob Private Model",
        provider="openai",
        api_base="https://api.bob.example/v1",
        api_key="sk-bob",
        model_name="bob-model",
        category="text",
        model_scope="user",
        owner_username="bob",
    )
    assert alice_model_id > 0
    assert bob_model_id > 0

    AiModelRepository.set_default(alice_model_id)
    assert AiModelRepository.get_default()["id"] == admin_default["id"]
    assert AiModelRepository.get_default(model_scope="user", owner_username="alice")["id"] == alice_model_id
    assert AiModelRepository.get_default(model_scope="user", owner_username="bob") is None

    admin_models, _ = AiModelRepository.get_all(model_scope="admin", owner_username="")
    assert alice_model_id not in {m["id"] for m in admin_models}
    assert bob_model_id not in {m["id"] for m in admin_models}

    alice_private, _ = AiModelRepository.get_all(model_scope="user", owner_username="alice")
    assert {m["id"] for m in alice_private} == {alice_model_id}

    alice_available, _ = AiModelRepository.get_available_for_user("alice", page_size=100)
    alice_ids = {m["id"] for m in alice_available}
    assert alice_model_id in alice_ids
    assert admin_default["id"] in alice_ids
    assert bob_model_id not in alice_ids

    assert AiModelRepository.get_accessible_by_id(alice_model_id, "alice") is not None
    assert AiModelRepository.get_accessible_by_id(admin_default["id"], "alice") is not None
    assert AiModelRepository.get_accessible_by_id(bob_model_id, "alice") is None


def test_model_grouping_templates_explain_separate_management():
    chat_template = Path("app/templates/user_chat.html").read_text(encoding="utf-8")
    quick_template = Path("app/templates/admin/model_quick_config.html").read_text(encoding="utf-8")
    admin_template = Path("app/templates/admin/model_list.html").read_text(encoding="utf-8")
    admin_controller = Path("app/controllers/admin_model.py").read_text(encoding="utf-8")

    assert 'label="我的模型配置"' in chat_template
    assert 'label="管理员提供模型"' in chat_template
    assert "user-model-switch" in quick_template
    assert "只管理“我的模型配置”分组" in quick_template
    assert "普通用户不会覆盖它们" in quick_template
    assert "仅管理“管理员提供模型”分组" in admin_template
    assert 'model_scope="admin"' in admin_controller
    assert 'model_scope="user"' in admin_controller
    assert "owner_username=self.current_user" in admin_controller


def test_quick_config_target_lookup_does_not_depend_on_handler_helper():
    from types import SimpleNamespace
    from app.controllers.admin_model import ModelQuickConfigHandler
    from app.models.ai_model import AiModelRepository

    model_id = AiModelRepository.create(
        name="Alice Fallback Model",
        provider="openai",
        api_base="https://api.alice.example/v1",
        api_key="sk-alice",
        model_name="alice-fallback",
        category="text",
        model_scope="user",
        owner_username="alice",
    )
    AiModelRepository.set_default(model_id)

    handler = SimpleNamespace(
        current_user="alice",
        get_body_argument=lambda name, default="": default,
    )
    model = ModelQuickConfigHandler._get_target_model(handler, source="body")
    assert model["id"] == model_id
    assert model["owner_username"] == "alice"


def test_conversation_create_rejects_disabled_or_foreign_user_models():
    from app.models.ai_model import AiModelRepository
    from pathlib import Path

    alice_id = AiModelRepository.create(
        name="Alice Disabled Model",
        provider="openai",
        api_base="https://api.alice.example/v1",
        api_key="sk-alice",
        model_name="alice-disabled",
        category="text",
        model_scope="user",
        owner_username="alice",
    )
    bob_id = AiModelRepository.create(
        name="Bob Private Model For Create",
        provider="openai",
        api_base="https://api.bob.example/v1",
        api_key="sk-bob",
        model_name="bob-private",
        category="text",
        model_scope="user",
        owner_username="bob",
    )
    assert AiModelRepository.toggle_enabled(alice_id) == 0

    alice_model = AiModelRepository.get_accessible_by_id(alice_id, "alice")
    bob_model_for_alice = AiModelRepository.get_accessible_by_id(bob_id, "alice")
    assert alice_model is not None
    assert alice_model.get("is_enabled") == 0
    assert bob_model_for_alice is None

    source = Path("app/controllers/user_chat.py").read_text(encoding="utf-8")
    create_handler = source[
        source.index("class UserConversationCreateHandler"):
        source.index("class UserConversationDeleteHandler")
    ]
    assert "except (ValueError, TypeError)" in create_handler
    assert "无效的模型ID" in create_handler
    assert "get_accessible_by_id" in create_handler
    assert 'model.get("is_enabled") == 0' in create_handler
