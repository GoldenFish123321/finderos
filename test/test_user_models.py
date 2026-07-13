"""
test_user_models.py — 用户模型单元测试

测试 UserRepository 的创建、验证、查询、更新、删除、批量操作。
借鉴林语瞳项目的基础测试实践。
"""

import os
import sys
import unittest
import tempfile

# 确保可以导入 app 模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.db import init_db, get_db
from app.models.user import UserRepository
from app.config.settings import settings


class TestUserRepository(unittest.TestCase):
    """用户仓库 CRUD 测试"""

    @classmethod
    def setUpClass(cls):
        """创建临时数据库用于测试。"""
        cls._tmpdir = tempfile.TemporaryDirectory()
        db_path = os.path.join(cls._tmpdir.name, "test.db")
        # 临时覆盖数据库路径
        cls._orig_db_path = settings.DB_PATH
        settings.DB_PATH = db_path
        # 确保数据库目录存在
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        init_db()

    @classmethod
    def tearDownClass(cls):
        """清理临时数据库。"""
        settings.DB_PATH = cls._orig_db_path
        cls._tmpdir.cleanup()

    def setUp(self):
        """每个测试前清空 users 表（保留 admin）。"""
        with get_db() as conn:
            conn.execute("DELETE FROM users WHERE username != 'admin'")
            conn.commit()

    # ---- 创建用户 ----

    def test_create_user_success(self):
        """测试成功创建用户。"""
        ok = UserRepository.create_user("testuser", "password123", role_id=2)
        self.assertTrue(ok)
        user = UserRepository.get_user_by_username("testuser")
        self.assertIsNotNone(user)
        self.assertEqual(user["username"], "testuser")

    def test_create_duplicate_user_fails(self):
        """测试重复用户名创建失败。"""
        ok1 = UserRepository.create_user("dupuser", "pass1")
        self.assertTrue(ok1)
        ok2 = UserRepository.create_user("dupuser", "pass2")
        self.assertFalse(ok2)

    # ---- 密码验证 ----

    def test_verify_correct_password(self):
        """测试正确密码验证通过。"""
        UserRepository.create_user("valid", "correct123")
        self.assertTrue(UserRepository.verify_user("valid", "correct123"))

    def test_verify_wrong_password(self):
        """测试错误密码验证失败。"""
        UserRepository.create_user("valid", "correct123")
        self.assertFalse(UserRepository.verify_user("valid", "wrongpass"))

    def test_verify_nonexistent_user(self):
        """测试不存在用户验证失败。"""
        self.assertFalse(UserRepository.verify_user("nobody", "anypass"))

    def test_verify_disabled_user(self):
        """测试禁用用户无法登录。"""
        UserRepository.create_user("disabled", "pass")
        with get_db() as conn:
            conn.execute("UPDATE users SET is_enabled = 0 WHERE username = ?", ("disabled",))
            conn.commit()
        self.assertFalse(UserRepository.verify_user("disabled", "pass"))

    # ---- 查询 ----

    def test_get_user_by_id(self):
        """测试按 ID 查询用户。"""
        UserRepository.create_user("byid", "pass")
        user = UserRepository.get_user_by_username("byid")
        fetched = UserRepository.get_user_by_id(user["id"])
        self.assertEqual(fetched["username"], "byid")

    def test_get_nonexistent_user(self):
        """测试查询不存在的用户返回 None。"""
        self.assertIsNone(UserRepository.get_user_by_id(99999))

    def test_get_user_count(self):
        """测试用户计数。"""
        initial = UserRepository.get_user_count()
        UserRepository.create_user("count1", "pass")
        UserRepository.create_user("count2", "pass")
        self.assertEqual(UserRepository.get_user_count(), initial + 2)

    def test_get_all_pagination(self):
        """测试分页查询。"""
        for i in range(5):
            UserRepository.create_user(f"pageuser{i}", "pass")
        rows, total = UserRepository.get_all(page=1, page_size=3)
        self.assertEqual(len(rows), 3)
        self.assertGreaterEqual(total, 5)

    def test_get_all_search(self):
        """测试搜索查询。"""
        UserRepository.create_user("searchme", "pass")
        UserRepository.create_user("other", "pass")
        rows, total = UserRepository.get_all(keyword="search")
        self.assertEqual(total, 1)
        self.assertEqual(rows[0]["username"], "searchme")

    # ---- 更新 ----

    def test_update_username(self):
        """测试更新用户名。"""
        UserRepository.create_user("oldname", "pass")
        user = UserRepository.get_user_by_username("oldname")
        ok = UserRepository.update_user(user["id"], username="newname")
        self.assertTrue(ok)
        self.assertIsNotNone(UserRepository.get_user_by_username("newname"))
        self.assertIsNone(UserRepository.get_user_by_username("oldname"))

    def test_update_password(self):
        """测试更新密码。"""
        UserRepository.create_user("pwuser", "oldpass")
        user = UserRepository.get_user_by_username("pwuser")
        UserRepository.update_user(user["id"], username="pwuser", password="newpass")
        self.assertTrue(UserRepository.verify_user("pwuser", "newpass"))
        self.assertFalse(UserRepository.verify_user("pwuser", "oldpass"))

    def test_update_duplicate_username_fails(self):
        """测试更新为已存在的用户名失败。"""
        UserRepository.create_user("a", "pass")
        UserRepository.create_user("b", "pass")
        user_b = UserRepository.get_user_by_username("b")
        ok = UserRepository.update_user(user_b["id"], username="a")
        self.assertFalse(ok)

    # ---- 删除 ----

    def test_delete_user(self):
        """测试删除普通用户。"""
        UserRepository.create_user("todelete", "pass")
        user = UserRepository.get_user_by_username("todelete")
        ok = UserRepository.delete_user(user["id"])
        self.assertTrue(UserRepository.get_user_by_username("todelete") is None)

    def test_cannot_delete_admin(self):
        """测试无法删除 admin。"""
        admin = UserRepository.get_user_by_username("admin")
        if admin:
            ok = UserRepository.delete_user(admin["id"])
            self.assertFalse(ok)

    # ---- 批量操作 ----

    def test_batch_delete(self):
        """测试批量删除。"""
        UserRepository.create_user("bd1", "pass")
        UserRepository.create_user("bd2", "pass")
        UserRepository.create_user("bd3", "pass")
        ids = [
            UserRepository.get_user_by_username("bd1")["id"],
            UserRepository.get_user_by_username("bd2")["id"],
        ]
        count = UserRepository.batch_delete(ids)
        self.assertEqual(count, 2)
        self.assertIsNone(UserRepository.get_user_by_username("bd1"))
        self.assertIsNone(UserRepository.get_user_by_username("bd2"))
        self.assertIsNotNone(UserRepository.get_user_by_username("bd3"))

    def test_batch_delete_excludes_admin(self):
        """测试批量删除排除 admin。"""
        admin = UserRepository.get_user_by_username("admin")
        if admin:
            UserRepository.create_user("batchuser", "pass")
            user = UserRepository.get_user_by_username("batchuser")
            count = UserRepository.batch_delete([admin["id"], user["id"]])
            self.assertEqual(count, 1)

    def test_batch_toggle(self):
        """测试批量禁用。"""
        UserRepository.create_user("bt1", "pass")
        UserRepository.create_user("bt2", "pass")
        ids = [
            UserRepository.get_user_by_username("bt1")["id"],
            UserRepository.get_user_by_username("bt2")["id"],
        ]
        count = UserRepository.batch_toggle(ids, enable=False)
        self.assertEqual(count, 2)
        self.assertFalse(UserRepository.verify_user("bt1", "pass"))

    # ---- 启用/禁用 ----

    def test_toggle_enabled(self):
        """测试单个用户启用/禁用切换。"""
        UserRepository.create_user("toggle", "pass")
        user = UserRepository.get_user_by_username("toggle")
        new_status = UserRepository.toggle_enabled(user["id"])
        self.assertEqual(new_status, 0)  # 变为禁用
        new_status2 = UserRepository.toggle_enabled(user["id"])
        self.assertEqual(new_status2, 1)  # 变为启用

    def test_toggle_admin_returns_minus2(self):
        """测试禁用 admin 返回 -2。"""
        admin = UserRepository.get_user_by_username("admin")
        if admin:
            self.assertEqual(UserRepository.toggle_enabled(admin["id"]), -2)


if __name__ == "__main__":
    unittest.main()
