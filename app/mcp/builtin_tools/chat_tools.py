"""
chat_tools.py — 对话管理类 MCP 工具处理函数

工具:
- list_conversations: 对话历史列表
- get_conversation_messages: 对话消息
"""

from typing import Any, Dict


def _list_conversations(username: str = "", limit: int = 20) -> Dict[str, Any]:
    """列出用户的对话历史。"""
    from app.models.conversation import ConversationRepository
    conversations = ConversationRepository.get_all(username=username, limit=limit)
    return {
        "total": len(conversations),
        "conversations": [
            {
                "id": c.get("id"),
                "title": c.get("title", "新对话"),
                "msg_count": c.get("msg_count", 0),
                "updated_at": c.get("updated_at", ""),
            }
            for c in conversations
        ],
    }


def _get_conversation_messages(conversation_id: int, limit: int = 20,
                               username: str = "") -> Dict[str, Any]:
    """获取指定对话的消息历史（含所有权验证）。"""
    from app.models.conversation import ConversationRepository
    if username:
        conv = ConversationRepository.get_by_id(conversation_id)
        if not conv or conv.get("username", "") != username:
            return {
                "conversation_id": conversation_id,
                "total": 0,
                "messages": [],
                "error": "对话不存在或无权访问",
            }
    messages = ConversationRepository.get_messages(conversation_id, limit=limit)
    return {
        "conversation_id": conversation_id,
        "total": len(messages),
        "messages": [
            {
                "role": m.get("role", ""),
                "content": (m.get("content", "") or "")[:2000],
                "token_count": m.get("token_count", 0),
                "created_at": m.get("created_at", ""),
            }
            for m in messages
        ],
    }
