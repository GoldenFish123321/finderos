import unittest
import os
import tempfile


class TestLocalApiRegistry(unittest.TestCase):
    """测试本地接口注册表。"""

    @classmethod
    def setUpClass(cls):
        os.environ["FINDEROS_DB"] = os.path.join(tempfile.gettempdir(), "test_registry.db")
        from app.models.db import init_db
        init_db()

    def test_sync_creates_18_interfaces(self):
        """sync 应创建18个本地系统接口。"""
        from app.services.local_api_registry import sync_local_api_interfaces
        sync_local_api_interfaces()
        from app.models.db import get_db
        with get_db() as conn:
            count = conn.execute(
                "SELECT COUNT(*) AS cnt FROM api_interfaces WHERE interface_type = 'local' AND is_system = 1"
            ).fetchone()["cnt"]
        self.assertEqual(count, 18, f"期望18, 实际{count}")

    def test_sync_is_idempotent(self):
        """再次 sync 不应重复插入。"""
        from app.services.local_api_registry import sync_local_api_interfaces
        sync_local_api_interfaces()
        from app.models.db import get_db
        with get_db() as conn:
            count = conn.execute(
                "SELECT COUNT(*) AS cnt FROM api_interfaces WHERE interface_type = 'local' AND is_system = 1"
            ).fetchone()["cnt"]
        self.assertEqual(count, 18, f"幂等性失败, 期望18, 实际{count}")

    def test_all_local_handlers_set(self):
        """所有本地接口应有 local_handler。"""
        from app.models.db import get_db
        with get_db() as conn:
            rows = conn.execute(
                "SELECT local_handler FROM api_interfaces WHERE interface_type = 'local' AND is_system = 1"
            ).fetchall()
        for row in rows:
            self.assertTrue(row["local_handler"], f"空 local_handler")
            self.assertIn("/", row["local_handler"], f"格式异常: {row['local_handler']}")

    @classmethod
    def tearDownClass(cls):
        db = os.environ.get("FINDEROS_DB", "")
        if db and os.path.exists(db):
            os.remove(db)


if __name__ == "__main__":
    unittest.main()
