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
    def get_all(username: str = "", limit: int = 50, include_all: bool = False) -> list:
        """获取对话列表（按更新时间倒序）。

        默认保持用户侧行为：只返回指定 username 的会话。
        管理侧可传 include_all=True 跨用户查看所有会话。
        """
        with get_db() as conn:
            where = ""
            params = []
            if not include_all:
                where = "WHERE c.username = ? "
                params.append(username)
            rows = conn.execute(
                "SELECT c.*, "
                "(SELECT COUNT(*) FROM conversation_messages WHERE conversation_id = c.id) as msg_count "
                "FROM conversations c "
                f"{where}"
                "ORDER BY c.updated_at DESC LIMIT ?",
                (*params, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def get_all_admin(page: int = 1, page_size: int = 20,
                      username: str = "", keyword: str = "") -> tuple:
        """管理侧分页查询所有用户会话，返回 (rows, total)。"""
        page = max(1, int(page or 1))
        page_size = max(1, min(int(page_size or 20), 100))
        conditions = []
        params = []
        if username:
            conditions.append("c.username = ?")
            params.append(username)
        if keyword:
            conditions.append("(c.title LIKE ? OR c.username LIKE ?)")
            like = f"%{keyword}%"
            params.extend([like, like])
        where = "WHERE " + " AND ".join(conditions) if conditions else ""

        with get_db() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) as cnt FROM conversations c {where}",
                params,
            ).fetchone()["cnt"]
            rows = conn.execute(
                f"""
                SELECT c.*,
                       (SELECT COUNT(*) FROM conversation_messages WHERE conversation_id = c.id) as msg_count,
                       (SELECT COALESCE(SUM(token_count), 0) FROM conversation_messages WHERE conversation_id = c.id) as token_total,
                       (SELECT created_at FROM conversation_messages WHERE conversation_id = c.id ORDER BY id ASC LIMIT 1) as first_message_at,
                       (SELECT created_at FROM conversation_messages WHERE conversation_id = c.id ORDER BY id DESC LIMIT 1) as last_message_at
                FROM conversations c
                {where}
                ORDER BY c.updated_at DESC, c.id DESC
                LIMIT ? OFFSET ?
                """,
                (*params, page_size, (page - 1) * page_size),
            ).fetchall()
        return [dict(r) for r in rows], total

    @staticmethod
    def get_usernames() -> list:
        """获取存在会话的用户列表。"""
        with get_db() as conn:
            rows = conn.execute(
                "SELECT DISTINCT username FROM conversations "
                "WHERE username IS NOT NULL AND username != '' "
                "ORDER BY username ASC"
            ).fetchall()
        return [r["username"] for r in rows]

    @staticmethod
    def get_admin_stats() -> dict:
        """获取管理侧会话统计。"""
        with get_db() as conn:
            total = conn.execute("SELECT COUNT(*) as cnt FROM conversations").fetchone()["cnt"]
            user_count = conn.execute(
                "SELECT COUNT(DISTINCT username) as cnt FROM conversations WHERE username IS NOT NULL AND username != ''"
            ).fetchone()["cnt"]
            message_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM conversation_messages"
            ).fetchone()["cnt"]
            token_total = conn.execute(
                "SELECT COALESCE(SUM(token_count), 0) as total FROM conversation_messages"
            ).fetchone()["total"]
        return {
            "total": total,
            "user_count": user_count,
            "message_count": message_count,
            "token_total": token_total or 0,
        }

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
