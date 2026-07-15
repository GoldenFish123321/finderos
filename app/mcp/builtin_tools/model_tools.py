"""
model_tools.py — AI 模型类 MCP 工具处理函数 (v0.10 新增)

工具:
- list_ai_models: AI 模型列表
- get_default_model: 获取默认模型
"""

from typing import Any, Dict


def _list_ai_models() -> Dict[str, Any]:
    """列出所有启用的 AI 模型。"""
    from app.models.ai_model import AiModelRepository
    models, _ = AiModelRepository.get_all(page=1, page_size=100, enabled_only=True)
    return {
        "total": len(models),
        "models": [
            {
                "id": m["id"],
                "name": m["name"],
                "provider": m.get("provider", ""),
                "model_name": m.get("model_name", ""),
                "category": m.get("category", "text"),
                "is_default": bool(m.get("is_default", 0)),
            }
            for m in models
        ],
    }


def _get_default_model() -> Dict[str, Any]:
    """获取当前默认 AI 模型。"""
    from app.models.ai_model import AiModelRepository
    model = AiModelRepository.get_default()
    if not model:
        return {"success": False, "error": "没有设置默认模型"}
    return {
        "success": True,
        "model": {
            "id": model["id"],
            "name": model["name"],
            "provider": model.get("provider", ""),
            "model_name": model.get("model_name", ""),
            "category": model.get("category", "text"),
        },
    }
