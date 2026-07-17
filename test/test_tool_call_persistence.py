"""
test_tool_call_persistence.py — 多轮工具调用持久化测试

验证 v1.6.1 修复：
1. 数据库列 tool_calls / tool_call_id 存在
2. add_message 支持新参数
3. get_recent_messages 正确还原 tool_calls / tool_call_id
4. 消息按时间顺序存储（user → assistant+tool_calls → tool → assistant）
"""
import json
import os
import pytest
import sqlite3
import tempfile

# 使用测试数据库
os.environ.setdefault("FINDEROS_DB_PATH", os.path.join(tempfile.gettempdir(), "test_tool_persistence.db"))


@pytest.fixture(autouse=True)
def setup_test_db():
    """每个测试前重建数据库。"""
    db_path = os.environ["FINDEROS_DB_PATH"]
    if os.path.exists(db_path):
        os.remove(db_path)
    from app.models.db import init_db
    init_db()
    yield
    # 清理
    try:
        os.remove(db_path)
    except Exception:
        pass


class TestToolCallPersistence:
    """工具调用持久化功能测试。"""

    def test_db_columns_exist(self):
        """验证 tool_calls 和 tool_call_id 列已通过迁移添加。"""
        from app.models.db import get_db
        with get_db() as conn:
            cols = {row["name"] for row in conn.execute(
                "PRAGMA table_info(conversation_messages)"
            ).fetchall()}
        assert "tool_calls" in cols, "tool_calls 列缺失"
        assert "tool_call_id" in cols, "tool_call_id 列缺失"

    def test_add_message_with_tool_calls(self):
        """验证 add_message 支持 tool_calls 参数。"""
        from app.models.conversation import ConversationRepository
        from app.models.db import get_db

        # 创建对话
        conv_id = ConversationRepository.create("测试对话", username="testuser")

        # 保存带 tool_calls 的 assistant 消息
        tool_calls_json = json.dumps([
            {"id": "call_001", "type": "function",
             "function": {"name": "search_warehouse", "arguments": '{"keyword":"AI"}'}}
        ], ensure_ascii=False)
        ConversationRepository.add_message(
            conv_id, "assistant", "我来帮你查询", 0,
            tool_calls=tool_calls_json
        )

        # 验证存储
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM conversation_messages WHERE conversation_id = ? AND role = ?",
                (conv_id, "assistant")
            ).fetchone()
        assert row is not None
        assert row["tool_calls"] == tool_calls_json

    def test_add_message_with_tool_call_id(self):
        """验证 add_message 支持 tool_call_id 参数。"""
        from app.models.conversation import ConversationRepository
        from app.models.db import get_db

        conv_id = ConversationRepository.create("测试对话", username="testuser")

        # 保存 tool 结果消息
        ConversationRepository.add_message(
            conv_id, "tool", '{"results": [{"title": "新闻1"}]}', 0,
            tool_call_id="call_001"
        )

        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM conversation_messages WHERE conversation_id = ? AND role = ?",
                (conv_id, "tool")
            ).fetchone()
        assert row is not None
        assert row["tool_call_id"] == "call_001"

    def test_get_recent_messages_restores_tool_calls(self):
        """验证 get_recent_messages 正确还原 tool_calls 为 Python 对象。"""
        from app.models.conversation import ConversationRepository

        conv_id = ConversationRepository.create("测试对话", username="testuser")

        # 模拟一个完整的工具调用轮次
        expected_tool_calls = [
            {"id": "call_001", "type": "function",
             "function": {"name": "search_warehouse", "arguments": '{"keyword":"AI"}'}}
        ]

        ConversationRepository.add_message(conv_id, "user", "查询AI相关数据", 0)
        ConversationRepository.add_message(
            conv_id, "assistant", "正在查询...", 0,
            tool_calls=json.dumps(expected_tool_calls, ensure_ascii=False)
        )
        ConversationRepository.add_message(
            conv_id, "tool", '{"results": ["数据1", "数据2"]}', 0,
            tool_call_id="call_001"
        )
        ConversationRepository.add_message(
            conv_id, "assistant", "查询到2条数据", 10
        )

        messages = ConversationRepository.get_recent_messages(conv_id, limit=10)

        # 验证消息数量
        assert len(messages) == 4

        # 验证 assistant 消息包含 tool_calls
        assistant_msg = messages[1]
        assert assistant_msg["role"] == "assistant"
        assert "tool_calls" in assistant_msg
        assert assistant_msg["tool_calls"] == expected_tool_calls

        # 验证 tool 消息包含 tool_call_id
        tool_msg = messages[2]
        assert tool_msg["role"] == "tool"
        assert tool_msg.get("tool_call_id") == "call_001"

    def test_get_recent_messages_without_tool_data(self):
        """验证没有 tool_calls/tool_call_id 的旧消息仍能正常加载。"""
        from app.models.conversation import ConversationRepository

        conv_id = ConversationRepository.create("测试对话", username="testuser")
        ConversationRepository.add_message(conv_id, "user", "你好", 0)
        ConversationRepository.add_message(conv_id, "assistant", "你好！有什么可以帮助你的？", 5)

        messages = ConversationRepository.get_recent_messages(conv_id, limit=10)

        assert len(messages) == 2
        # 旧消息不应包含 tool_calls 或 tool_call_id
        assert "tool_calls" not in messages[0]
        assert "tool_call_id" not in messages[0]
        assert "tool_calls" not in messages[1]
        assert "tool_call_id" not in messages[1]

    def test_message_order_is_correct(self):
        """验证消息按时间顺序存储：user → assistant(tool_calls) → tool → assistant。"""
        from app.models.conversation import ConversationRepository
        from app.models.db import get_db

        conv_id = ConversationRepository.create("测试对话", username="testuser")

        # 模拟完整的工具调用流程
        ConversationRepository.add_message(conv_id, "user", "搜索新闻", 0)
        ConversationRepository.add_message(
            conv_id, "assistant", "", 0,
            tool_calls=json.dumps([{
                "id": "call_001", "type": "function",
                "function": {"name": "search_warehouse", "arguments": '{"keyword":"新闻"}'}
            }], ensure_ascii=False)
        )
        ConversationRepository.add_message(
            conv_id, "tool", '{"results": []}', 0,
            tool_call_id="call_001"
        )
        ConversationRepository.add_message(
            conv_id, "assistant", "未找到相关新闻", 5
        )

        # 验证 DB 中的顺序
        with get_db() as conn:
            rows = conn.execute(
                "SELECT role, tool_calls, tool_call_id FROM conversation_messages "
                "WHERE conversation_id = ? ORDER BY id ASC",
                (conv_id,)
            ).fetchall()

        roles = [r["role"] for r in rows]
        assert roles == ["user", "assistant", "tool", "assistant"], \
            f"消息顺序不正确: {roles}"

        # 验证 get_recent_messages 返回正确格式
        messages = ConversationRepository.get_recent_messages(conv_id, limit=10)
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"
        assert "tool_calls" in messages[1]
        assert messages[2]["role"] == "tool"
        assert messages[2].get("tool_call_id") == "call_001"
        assert messages[3]["role"] == "assistant"

    def test_add_message_backward_compatible(self):
        """验证 add_message 向后兼容 — 不传新参数时行为不变。"""
        from app.models.conversation import ConversationRepository
        from app.models.db import get_db

        conv_id = ConversationRepository.create("测试对话", username="testuser")
        ConversationRepository.add_message(conv_id, "user", "老版本消息", 0)

        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM conversation_messages WHERE conversation_id = ?",
                (conv_id,)
            ).fetchone()

        assert row is not None
        assert row["role"] == "user"
        assert row["content"] == "老版本消息"
        # 新列为 NULL（默认值）
        assert row["tool_calls"] is None
        assert row["tool_call_id"] is None
