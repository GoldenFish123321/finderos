"""
test_mcp_context.py — MCP 上下文传递测试 (contextvars)

验证:
  - set_mcp_context / clear_mcp_context 基本功能
  - 上下文更新/合并
  - 协程隔离（异步安全）
  - _inject_context 参数注入

关联 Issue: #30 — MCP上下文通过猴补丁传递，改用 contextvars
"""
import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.mcp.client import set_mcp_context, clear_mcp_context, _mcp_context_var


class TestMCPContextBasic(unittest.TestCase):
    """基本 set/clear/get 功能测试。"""

    def setUp(self):
        clear_mcp_context()

    def tearDown(self):
        clear_mcp_context()

    def test_set_and_get(self):
        """设置上下文后应能正确读取。"""
        set_mcp_context(username="testuser")
        ctx = _mcp_context_var.get()
        self.assertEqual(ctx["username"], "testuser")

    def test_clear(self):
        """清除后上下文应为空。"""
        set_mcp_context(username="testuser")
        clear_mcp_context()
        ctx = _mcp_context_var.get()
        self.assertEqual(ctx, {})

    def test_update_merge(self):
        """多次设置应合并键值。"""
        set_mcp_context(username="user1")
        set_mcp_context(role="admin")
        ctx = _mcp_context_var.get()
        self.assertEqual(ctx["username"], "user1")
        self.assertEqual(ctx["role"], "admin")

    def test_overwrite_key(self):
        """同键覆盖。"""
        set_mcp_context(username="user1")
        set_mcp_context(username="user2")
        ctx = _mcp_context_var.get()
        self.assertEqual(ctx["username"], "user2")

    def test_default_empty(self):
        """未设置时应返回空字典。"""
        ctx = _mcp_context_var.get()
        self.assertEqual(ctx, {})


class TestMCPContextAsync(unittest.TestCase):
    """协程隔离测试。"""

    def setUp(self):
        clear_mcp_context()

    def tearDown(self):
        clear_mcp_context()

    def test_async_context_isolation(self):
        """不同协程应各自拥有独立的上下文副本。"""

        async def task(name: str):
            set_mcp_context(username=name)
            await asyncio.sleep(0.01)
            return _mcp_context_var.get()

        async def main():
            set_mcp_context(username="main_user")
            results = await asyncio.gather(
                task("task_a"),
                task("task_b"),
            )
            main_ctx = _mcp_context_var.get()
            return results, main_ctx

        results, main_ctx = asyncio.run(main())

        # 各 task 应有自己的 username
        self.assertEqual(results[0]["username"], "task_a")
        self.assertEqual(results[1]["username"], "task_b")
        # 主协程上下文未被污染
        self.assertEqual(main_ctx["username"], "main_user")


class TestMCPContextInject(unittest.TestCase):
    """_inject_context 参数注入测试。"""

    def setUp(self):
        clear_mcp_context()

    def tearDown(self):
        clear_mcp_context()

    def test_inject_username_for_conversation_tools(self):
        """对 list_conversations 工具应注入 username。"""
        from app.mcp.client import MCPClient
        client = MCPClient()
        set_mcp_context(username="ctxuser")

        # list_conversations
        args = client._inject_context({}, "list_conversations")
        self.assertEqual(args.get("username"), "ctxuser")

        # get_conversation_messages
        args = client._inject_context({}, "get_conversation_messages")
        self.assertEqual(args.get("username"), "ctxuser")

    def test_no_inject_for_other_tools(self):
        """非对话管理工具不应注入 username。"""
        from app.mcp.client import MCPClient
        client = MCPClient()
        set_mcp_context(username="ctxuser")

        args = client._inject_context({}, "search_warehouse")
        self.assertNotIn("username", args)

    def test_no_inject_when_context_empty(self):
        """无上下文时不注入任何参数。"""
        from app.mcp.client import MCPClient
        client = MCPClient()
        # 不设置上下文
        args = client._inject_context({}, "list_conversations")
        self.assertNotIn("username", args)

    def test_no_override_existing_username(self):
        """已有参数不应被覆盖。"""
        from app.mcp.client import MCPClient
        client = MCPClient()
        set_mcp_context(username="ctxuser")

        args = client._inject_context(
            {"username": "explicit_user"}, "list_conversations"
        )
        self.assertEqual(args["username"], "explicit_user")


if __name__ == "__main__":
    unittest.main()
