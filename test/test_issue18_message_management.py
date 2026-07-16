"""
test_issue18_message_management.py — Issue #18: 管理侧消息管理测试

验证消息管理控制器的核心功能：
- 多维度筛选（用户/角色/关键字/敏感/审核状态/时间范围）
- 消息标记操作（敏感标记/审核状态变更）
- 单条和批量删除
- 权限校验
- 数据库迁移
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.conversation import ConversationRepository
from app.models.db import get_db, init_db, seed_default_data


class TestIssue18MessageManagement(unittest.TestCase):
    """Issue #18: 管理侧独立消息管理核心功能测试。"""

    @classmethod
    def setUpClass(cls):
        """初始化测试数据库。"""
        init_db()
        seed_default_data()

    def setUp(self):
        """每个测试前创建测试数据。"""
        # 创建测试会话和消息
        with get_db() as conn:
            # 确保测试用户存在
            conn.execute(
                "INSERT OR IGNORE INTO users (id, username, password_hash, salt, role_id, is_enabled) "
                "VALUES (999, 'test_msg_user', 'hash', 'salt', 1, 1)"
            )
            # 创建测试会话
            conn.execute(
                "INSERT OR IGNORE INTO conversations (id, title, username) "
                "VALUES (9999, 'Test Conversation', 'test_msg_user')"
            )
            # 创建测试消息（先清后插）
            conn.execute("DELETE FROM conversation_messages WHERE conversation_id = 9999")
            conn.execute(
                "INSERT INTO conversation_messages (id, conversation_id, role, content, token_count) "
                "VALUES (99991, 9999, 'user', '这是用户消息1', 10)"
            )
            conn.execute(
                "INSERT INTO conversation_messages (id, conversation_id, role, content, token_count) "
                "VALUES (99992, 9999, 'assistant', '这是AI回复1', 20)"
            )
            conn.execute(
                "INSERT INTO conversation_messages (id, conversation_id, role, content, token_count) "
                "VALUES (99993, 9999, 'user', '这是用户消息2', 15)"
            )
            conn.commit()

    # ════════════════════════════════════════════════════════════
    # 数据库迁移验证
    # ════════════════════════════════════════════════════════════

    def test_db_columns_exist(self):
        """验证 conversation_messages 表包含 is_sensitive 和 review_status 列。"""
        with get_db() as conn:
            cols = conn.execute("PRAGMA table_info(conversation_messages)").fetchall()
            col_names = [c["name"] for c in cols]
        self.assertIn("is_sensitive", col_names, "is_sensitive column missing")
        self.assertIn("review_status", col_names, "review_status column missing")

    def test_db_defaults(self):
        """验证新列的默认值正确。"""
        with get_db() as conn:
            row = conn.execute(
                "SELECT is_sensitive, review_status FROM conversation_messages WHERE id = 99991"
            ).fetchone()
        self.assertEqual(row["is_sensitive"], 0, "Default is_sensitive should be 0")
        self.assertEqual(row["review_status"], "pending", "Default review_status should be 'pending'")

    # ════════════════════════════════════════════════════════════
    # 消息统计
    # ════════════════════════════════════════════════════════════

    def test_get_message_stats(self):
        """验证消息统计功能。"""
        stats = ConversationRepository.get_message_stats()
        self.assertIn("total", stats)
        self.assertIn("sensitive", stats)
        self.assertIn("pending", stats)
        self.assertIn("flagged", stats)
        self.assertIsInstance(stats["total"], int)

    # ════════════════════════════════════════════════════════════
    # 消息列表查询
    # ════════════════════════════════════════════════════════════

    def test_get_all_messages_admin(self):
        """验证跨会话消息查询。"""
        msgs, total = ConversationRepository.get_all_messages_admin(page=1, page_size=10)
        self.assertIsInstance(msgs, list)
        self.assertIsInstance(total, int)
        if msgs:
            self.assertIn("username", msgs[0], "username missing in join result")
            self.assertIn("conversation_title", msgs[0], "conversation_title missing")
            self.assertIn("content", msgs[0], "content missing")

    def test_filter_by_role(self):
        """验证按角色筛选。"""
        user_msgs, _ = ConversationRepository.get_all_messages_admin(page=1, page_size=10, role="user")
        for m in user_msgs:
            self.assertEqual(m["role"], "user")

        ai_msgs, _ = ConversationRepository.get_all_messages_admin(page=1, page_size=10, role="assistant")
        for m in ai_msgs:
            self.assertEqual(m["role"], "assistant")

    def test_filter_by_keyword(self):
        """验证按关键字搜索。"""
        msgs, _ = ConversationRepository.get_all_messages_admin(page=1, page_size=10, keyword="用户消息1")
        self.assertGreater(len(msgs), 0, "Should find message with keyword")
        self.assertIn("用户消息1", msgs[0]["content"])

    def test_filter_by_username(self):
        """验证按用户名筛选。"""
        msgs, _ = ConversationRepository.get_all_messages_admin(
            page=1, page_size=10, username="test_msg_user"
        )
        for m in msgs:
            self.assertEqual(m.get("username"), "test_msg_user")

    def test_filter_by_sensitive(self):
        """验证按敏感标记筛选。"""
        # 先标记一条消息为敏感
        ConversationRepository.mark_message_sensitive(99992, 1)
        try:
            msgs, _ = ConversationRepository.get_all_messages_admin(
                page=1, page_size=10, is_sensitive="1"
            )
            for m in msgs:
                self.assertEqual(m["is_sensitive"], 1)
        finally:
            ConversationRepository.mark_message_sensitive(99992, 0)

    def test_filter_by_review_status(self):
        """验证按审核状态筛选。"""
        ConversationRepository.mark_message_reviewed(99991, "reviewed")
        try:
            msgs, _ = ConversationRepository.get_all_messages_admin(
                page=1, page_size=10, review_status="reviewed"
            )
            for m in msgs:
                self.assertEqual(m["review_status"], "reviewed")
        finally:
            ConversationRepository.mark_message_reviewed(99991, "pending")

    def test_pagination(self):
        """验证分页功能。"""
        page1, total = ConversationRepository.get_all_messages_admin(page=1, page_size=1)
        page2, _ = ConversationRepository.get_all_messages_admin(page=2, page_size=1)
        if total >= 2:
            self.assertEqual(len(page1), 1)
            self.assertEqual(len(page2), 1)
            self.assertNotEqual(page1[0]["id"], page2[0]["id"], "Pages should return different items")

    def test_get_message_usernames(self):
        """验证获取有消息的用户列表。"""
        usernames = ConversationRepository.get_message_usernames()
        self.assertIsInstance(usernames, list)
        self.assertIn("test_msg_user", usernames)

    # ════════════════════════════════════════════════════════════
    # 标记操作
    # ════════════════════════════════════════════════════════════

    def test_mark_sensitive(self):
        """验证敏感标记操作。"""
        result = ConversationRepository.mark_message_sensitive(99991, 1)
        self.assertTrue(result, "Should return True for existing message")
        try:
            with get_db() as conn:
                row = conn.execute(
                    "SELECT is_sensitive FROM conversation_messages WHERE id = 99991"
                ).fetchone()
            self.assertEqual(row["is_sensitive"], 1)
        finally:
            ConversationRepository.mark_message_sensitive(99991, 0)

    def test_unmark_sensitive(self):
        """验证取消敏感标记。"""
        ConversationRepository.mark_message_sensitive(99991, 1)
        result = ConversationRepository.mark_message_sensitive(99991, 0)
        self.assertTrue(result)
        with get_db() as conn:
            row = conn.execute(
                "SELECT is_sensitive FROM conversation_messages WHERE id = 99991"
            ).fetchone()
        self.assertEqual(row["is_sensitive"], 0)

    def test_mark_nonexistent_message(self):
        """验证标记不存在的消息返回 False。"""
        result = ConversationRepository.mark_message_sensitive(999999, 1)
        self.assertFalse(result, "Should return False for nonexistent message")

    def test_mark_reviewed(self):
        """验证审核状态变更。"""
        result = ConversationRepository.mark_message_reviewed(99991, "reviewed")
        self.assertTrue(result)
        try:
            with get_db() as conn:
                row = conn.execute(
                    "SELECT review_status FROM conversation_messages WHERE id = 99991"
                ).fetchone()
            self.assertEqual(row["review_status"], "reviewed")
        finally:
            ConversationRepository.mark_message_reviewed(99991, "pending")

    def test_mark_flagged(self):
        """验证标记操作。"""
        result = ConversationRepository.mark_message_reviewed(99992, "flagged")
        self.assertTrue(result)
        try:
            with get_db() as conn:
                row = conn.execute(
                    "SELECT review_status FROM conversation_messages WHERE id = 99992"
                ).fetchone()
            self.assertEqual(row["review_status"], "flagged")
        finally:
            ConversationRepository.mark_message_reviewed(99992, "pending")

    def test_mark_cleared(self):
        """验证排除操作。"""
        result = ConversationRepository.mark_message_reviewed(99993, "cleared")
        self.assertTrue(result)
        try:
            with get_db() as conn:
                row = conn.execute(
                    "SELECT review_status FROM conversation_messages WHERE id = 99993"
                ).fetchone()
            self.assertEqual(row["review_status"], "cleared")
        finally:
            ConversationRepository.mark_message_reviewed(99993, "pending")

    def test_invalid_review_status_rejected(self):
        """验证无效审核状态被拒绝。"""
        result = ConversationRepository.mark_message_reviewed(99991, "invalid_status")
        self.assertTrue(result)  # 操作成功但会被纠正
        with get_db() as conn:
            row = conn.execute(
                "SELECT review_status FROM conversation_messages WHERE id = 99991"
            ).fetchone()
        self.assertEqual(row["review_status"], "reviewed", "Should default to 'reviewed'")

    # ════════════════════════════════════════════════════════════
    # 删除操作
    # ════════════════════════════════════════════════════════════

    def test_delete_message(self):
        """验证删除单条消息。"""
        # 创建一个临时消息用于删除测试
        with get_db() as conn:
            conn.execute(
                "INSERT INTO conversation_messages (conversation_id, role, content) "
                "VALUES (9999, 'user', '临时消息')"
            )
            temp_id = conn.execute("SELECT last_insert_rowid() as id").fetchone()["id"]
        result = ConversationRepository.delete_message(temp_id)
        self.assertTrue(result, "Should successfully delete message")
        with get_db() as conn:
            row = conn.execute(
                "SELECT id FROM conversation_messages WHERE id = ?", (temp_id,)
            ).fetchone()
        self.assertIsNone(row, "Message should not exist after deletion")

    def test_delete_nonexistent_message(self):
        """验证删除不存在的消息返回 False。"""
        result = ConversationRepository.delete_message(999999)
        self.assertFalse(result)

    # ════════════════════════════════════════════════════════════
    # 种子数据
    # ════════════════════════════════════════════════════════════

    def test_message_manage_function_seeded(self):
        """验证消息管理功能节点已种子化。"""
        with get_db() as conn:
            func = conn.execute(
                "SELECT * FROM functions WHERE route_path = '/admin/message'"
            ).fetchone()
        self.assertIsNotNone(func, "Message management function should be seeded")
        self.assertEqual(func["name"], "消息管理")

    def test_indexes_exist(self):
        """验证新索引已创建。"""
        with get_db() as conn:
            indexes = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE '%conv_msgs%'"
            ).fetchall()
            index_names = [i["name"] for i in indexes]
        self.assertIn("idx_conv_msgs_sensitive", index_names)
        self.assertIn("idx_conv_msgs_review", index_names)

    @classmethod
    def tearDownClass(cls):
        """清理测试数据。"""
        with get_db() as conn:
            conn.execute("DELETE FROM conversation_messages WHERE conversation_id = 9999")
            conn.execute("DELETE FROM conversations WHERE id = 9999")
            conn.execute("DELETE FROM users WHERE id = 999")
            conn.commit()


if __name__ == "__main__":
    unittest.main(verbosity=2)
