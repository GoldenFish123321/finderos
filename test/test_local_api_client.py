import unittest
import os
import sys
import tempfile

# 设置测试数据库
os.environ["FINDEROS_DB"] = os.path.join(tempfile.gettempdir(), "test_local_api.db")


class TestLocalApiClient(unittest.TestCase):
    """测试本地接口客户端。"""

    @classmethod
    def setUpClass(cls):
        """初始化测试环境：创建DB + 注册handlers。"""
        from app.models.db import init_db
        init_db()
        from app.services.local_api_client import _init_local_handlers
        _init_local_handlers()

    def test_init_registers_all_builtin_handlers(self):
        """内置 handler 应全部注册，外部代理可在同一注册表中共存。"""
        from app.services.local_api_client import _LOCAL_HANDLER_MAP
        count = len(_LOCAL_HANDLER_MAP)
        self.assertGreaterEqual(count, 21, f"期望至少21个handler, 实际{count}个")

    def test_all_expected_handler_keys(self):
        """所有预期handler key都应注册。"""
        from app.services.local_api_client import _LOCAL_HANDLER_MAP
        expected = [
            "warehouse/search", "warehouse/recent", "warehouse/stats",
            "warehouse/fulltext", "warehouse/by_id",
            "collect/web", "collect/deep", "collect/sources",
            "employee/list", "employee/invoke",
            "model/list", "model/default",
            "conversation/list", "conversation/messages",
            "crawl4ai/collect", "crawl4ai/batch",
            "system/stats", "skill/load",
            "collector/fetch", "collector/deep-fetch", "music/netease",
        ]
        for key in expected:
            self.assertIn(key, _LOCAL_HANDLER_MAP, f"缺少handler: {key}")

    def test_call_nonexistent_handler(self):
        """调用不存在的handler应返回错误。"""
        from app.services.local_api_client import call_local_api
        import asyncio
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(
            call_local_api("nonexistent_handler", {})
        )
        loop.close()
        self.assertFalse(result["success"])
        self.assertIn("未注册", result["error"])

    def test_external_url_template_supports_seed_and_admin_formats(self):
        from app.services.local_api_client import _render_url_template

        self.assertEqual(
            _render_url_template(
                "https://example.test/{message}?copy={{message}}",
                {"message": "北京 天气"},
            ),
            "https://example.test/%E5%8C%97%E4%BA%AC%20%E5%A4%A9%E6%B0%94"
            "?copy=%E5%8C%97%E4%BA%AC%20%E5%A4%A9%E6%B0%94",
        )

    def test_register_and_call_custom_handler(self):
        """注册自定义handler后应能调用。"""
        from app.services.local_api_client import register_local_handler, call_local_api
        import asyncio

        def _test_handler(name="world"):
            return {"greeting": f"hello {name}"}

        register_local_handler("test/custom", _test_handler)
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(
            call_local_api("test/custom", {"name": "hermes"})
        )
        loop.close()
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["greeting"], "hello hermes")

    @classmethod
    def tearDownClass(cls):
        import os
        db = os.environ.get("FINDEROS_DB", "")
        if db and os.path.exists(db):
            os.remove(db)


if __name__ == "__main__":
    unittest.main()
