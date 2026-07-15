"""
conversation.py — 对话管理 Repository

支持多轮对话上下文记忆与历史记录保存。
"""
from app.models.db import get_db


class ConversationRepository:
    """对话管理数据访问类。"""

    @staticmethod
    def create(title: str = "新对话", model_id: int = None, username: str = "") -> int:
        """创建新对话，返回对话 ID。"""
        with get_db() as conn:
            cur = conn.execute(
                "INSERT INTO conversations (title, model_id, username) VALUES (?, ?, ?)",
                (title, model_id, username),
            )
            conn.commit()
            return cur.lastrowid

    @staticmethod
    def get_all(username: str = "", limit: int = 50) -> list:
        """获取用户的对话列表（按更新时间倒序）。"""
        with get_db() as conn:
            rows = conn.execute(
                "SELECT c.*, "
                "(SELECT COUNT(*) FROM conversation_messages WHERE conversation_id = c.id) as msg_count "
                "FROM conversations c "
                "WHERE c.username = ? "
                "ORDER BY c.updated_at DESC LIMIT ?",
                (username, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def get_by_id(conv_id: int):
        """获取对话详情。"""
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM conversations WHERE id = ?", (conv_id,)
            ).fetchone()
            return dict(row) if row else None

    @staticmethod
    def update_title(conv_id: int, title: str) -> bool:
        """更新对话标题。"""
        with get_db() as conn:
            conn.execute(
                "UPDATE conversations SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (title, conv_id),
            )
            conn.commit()
        return True

    @staticmethod
    def touch(conv_id: int):
        """更新对话的 updated_at 时间戳。"""
        with get_db() as conn:
            conn.execute(
                "UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (conv_id,),
            )
            conn.commit()

    @staticmethod
    def delete(conv_id: int) -> bool:
        """删除对话及其所有消息（CASCADE）。"""
        with get_db() as conn:
            conn.execute("DELETE FROM conversation_messages WHERE conversation_id = ?", (conv_id,))
            conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
            conn.commit()
            return True

    @staticmethod
    def add_message(conv_id: int, role: str, content: str, token_count: int = 0):
        """向对话中添加一条消息。"""
        with get_db() as conn:
            conn.execute(
                "INSERT INTO conversation_messages (conversation_id, role, content, token_count) "
                "VALUES (?, ?, ?, ?)",
                (conv_id, role, content, token_count),
            )
            # 同时更新对话时间戳
            conn.execute(
                "UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (conv_id,),
            )
            conn.commit()

    @staticmethod
    def get_messages(conv_id: int, limit: int = 20) -> list:
        """获取对话的最近 N 条消息（按时间正序）。"""
        with get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM ("
                "  SELECT * FROM conversation_messages WHERE conversation_id = ? "
                "  ORDER BY id DESC LIMIT ?"
                ") ORDER BY id ASC",
                (conv_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def get_recent_messages(conv_id: int, limit: int = 10) -> list:
        """获取对话最近 N 条消息，返回 (role, content) 列表。"""
        messages = ConversationRepository.get_messages(conv_id, limit)
        return [{"role": m["role"], "content": m["content"]} for m in messages]
