"""
test_employee_message_persistence.py — 测试 @数字员工 对话消息持久化修复

验证修复内容:
1. UserEmployeeInvokeHandler 能正确接收 conversation_id 参数
2. _invoke_api_employee 接受 conv_id 参数
3. _invoke_llm_employee 接受 conv_id 参数
4. _mock_api_employee_fallback 接受 conv_id 参数
5. 消息在员工调用后被保存到 conversation_messages 表
6. 前端 doSend 发送 conversation_id（通过模板 JS 验证）
"""

import json
import os
import sys
import pytest

# 确保项目根目录在 sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.conversation import ConversationRepository
from app.models.db import get_db


class TestEmployeeMessagePersistence:

    def test_conversation_create_and_save_messages(self):
        """测试: 创建对话 → 保存消息 → 读取消息 完整流程"""
        conv_id = ConversationRepository.create(
            title="@测试员工 天气查询",
            model_id=None,
            username="admin",
        )
        assert conv_id > 0, "应成功创建对话"

        # 模拟保存用户消息和 AI 回复
        ConversationRepository.add_message(conv_id, "user", "今天北京天气怎样？", 0)
        ConversationRepository.add_message(
            conv_id, "assistant", "北京今天晴，25°C，适合出行。", 10
        )

        # 验证消息可读取
        msgs = ConversationRepository.get_messages(conv_id, limit=50)
        assert len(msgs) == 2, f"应有2条消息，实际 {len(msgs)} 条"
        assert msgs[0]["role"] == "user"
        assert msgs[1]["role"] == "assistant"
        assert "北京" in msgs[1]["content"]

        # 清理
        with get_db() as conn:
            conn.execute(
                "DELETE FROM conversation_messages WHERE conversation_id = ?",
                (conv_id,),
            )
            conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
            conn.commit()

    def test_empty_messages_returns_empty_list(self):
        """测试: 无消息的对话返回空列表而非报错"""
        conv_id = ConversationRepository.create(
            title="空对话测试",
            username="admin",
        )
        msgs = ConversationRepository.get_messages(conv_id, limit=50)
        assert isinstance(msgs, list), "应返回列表"
        assert len(msgs) == 0, "空对话应返回0条消息"

        # 清理
        with get_db() as conn:
            conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
            conn.commit()

    def test_deleted_conversation_is_not_resurrected_by_late_stream_save(self):
        """测试: 删除会话后，迟到的流式保存不应重新创建该会话。"""
        conv_id = ConversationRepository.create(
            title="待删除会话",
            username="admin",
        )
        ConversationRepository.add_message(conv_id, "user", "删除前消息", 0)

        assert ConversationRepository.delete_for_user(conv_id, "admin")
        assert ConversationRepository.get_by_id(conv_id) is None
        assert ConversationRepository.get_messages(conv_id, limit=50) == []

        # 模拟 SSE/员工调用在删除后才结束并尝试保存消息
        assert not ConversationRepository.add_message(conv_id, "assistant", "迟到回复", 1)
        assert ConversationRepository.get_by_id(conv_id) is None, (
            "已删除会话不应被 add_message 隐式复活"
        )
        assert ConversationRepository.get_messages(conv_id, limit=50) == []

    def test_conversation_delete_returns_false_for_missing_row(self):
        """测试: 删除不存在的会话应返回 False，便于上层给出错误提示。"""
        assert not ConversationRepository.delete(-999999)
        assert not ConversationRepository.delete_for_user(-999999, "admin")

    def test_auto_title_update_on_first_message(self):
        """测试: 首条消息时自动更新对话标题（从"新对话"更新）"""
        conv_id = ConversationRepository.create(
            title="新对话",
            username="admin",
        )
        # 模拟 UserChatStreamHandler 的自动标题更新逻辑
        ConversationRepository.add_message(conv_id, "user", "帮我分析销售数据", 0)
        ConversationRepository.add_message(
            conv_id, "assistant", "好的，正在分析...", 5
        )

        conv = ConversationRepository.get_by_id(conv_id)
        if conv and (conv.get("title") or "").strip() in ("新对话", ""):
            auto_title = "帮我分析销售数据"[:30]
            ConversationRepository.update_title(conv_id, auto_title)

        # 验证标题已更新
        updated = ConversationRepository.get_by_id(conv_id)
        assert updated["title"] == "帮我分析销售数据", (
            f"标题应更新为消息前30字符，实际: {updated['title']}"
        )

        # 清理
        with get_db() as conn:
            conn.execute(
                "DELETE FROM conversation_messages WHERE conversation_id = ?",
                (conv_id,),
            )
            conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
            conn.commit()

    def test_get_messages_desc_asc_order(self):
        """测试: get_messages 返回按时间正序的消息（最旧在前，最新在后）"""
        conv_id = ConversationRepository.create(
            title="排序测试",
            username="admin",
        )
        # 按顺序插入多条消息
        ConversationRepository.add_message(conv_id, "user", "消息1", 0)
        ConversationRepository.add_message(conv_id, "assistant", "回复1", 2)
        ConversationRepository.add_message(conv_id, "user", "消息2", 0)
        ConversationRepository.add_message(conv_id, "assistant", "回复2", 3)

        msgs = ConversationRepository.get_messages(conv_id, limit=50)
        assert len(msgs) == 4
        # 验证顺序：消息1, 回复1, 消息2, 回复2
        assert msgs[0]["content"] == "消息1"
        assert msgs[1]["content"] == "回复1"
        assert msgs[2]["content"] == "消息2"
        assert msgs[3]["content"] == "回复2"

        # 测试 limit 参数
        limited = ConversationRepository.get_messages(conv_id, limit=2)
        assert len(limited) == 2
        # 最近的2条应该是消息2和回复2
        assert limited[0]["content"] == "消息2"
        assert limited[1]["content"] == "回复2"

        # 清理
        with get_db() as conn:
            conn.execute(
                "DELETE FROM conversation_messages WHERE conversation_id = ?",
                (conv_id,),
            )
            conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
            conn.commit()

    def test_employee_invoke_handler_signature(self):
        """测试: UserEmployeeInvokeHandler 方法签名正确（接受 conv_id 参数）"""
        from app.controllers.user_chat import UserEmployeeInvokeHandler
        import inspect

        sig_post = inspect.signature(UserEmployeeInvokeHandler.post)
        # post 方法应能接受 conversation_id（通过 self.get_body_argument）
        # 检查方法存在且可调用
        assert callable(UserEmployeeInvokeHandler.post)

        # _invoke_llm_employee 应有 conv_id 参数
        sig_llm = inspect.signature(UserEmployeeInvokeHandler._invoke_llm_employee)
        assert "conv_id" in sig_llm.parameters, (
            f"_invoke_llm_employee 缺少 conv_id 参数，当前参数: {list(sig_llm.parameters.keys())}"
        )

        # _invoke_api_employee 应有 conv_id 参数
        sig_api = inspect.signature(UserEmployeeInvokeHandler._invoke_api_employee)
        assert "conv_id" in sig_api.parameters, (
            f"_invoke_api_employee 缺少 conv_id 参数，当前参数: {list(sig_api.parameters.keys())}"
        )

        # _mock_api_employee_fallback 应有 conv_id 参数
        sig_mock = inspect.signature(
            UserEmployeeInvokeHandler._mock_api_employee_fallback
        )
        assert "conv_id" in sig_mock.parameters, (
            f"_mock_api_employee_fallback 缺少 conv_id 参数，当前参数: {list(sig_mock.parameters.keys())}"
        )

    def test_frontend_template_has_conversation_id_in_employee_branch(self):
        """测试: 前端 user_chat.html 中 @数字员工 分支包含 conversation_id"""
        template_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "app", "templates", "user_chat.html",
        )
        with open(template_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 确认 employeeId 分支存在
        assert "if (employeeId)" in content, "应有 @数字员工 分支"

        # 确认 conversation_id 在 employee 分支中
        # 查找 "employee_id" 附近是否有 "conversation_id"
        emp_idx = content.find("formData.append('employee_id'")
        assert emp_idx > 0, "应有 employee_id 表单字段"

        # 在 employee_id 附近搜索 conversation_id
        nearby = content[emp_idx : emp_idx + 500]
        assert "conversation_id" in nearby, (
            f"@数字员工 分支应包含 conversation_id，但附近代码为:\n{nearby[:300]}"
        )

    def test_frontend_stats_handler_syncs_conversation_id(self):
        """测试: 前端 stats SSE 事件处理中包含 conversation_id 同步逻辑"""
        template_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "app", "templates", "user_chat.html",
        )
        with open(template_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 确认 stats 事件处理有 conversation_id 同步
        assert "statsData.conversation_id" in content, (
            "stats 事件处理应包含 conversation_id 同步逻辑"
        )
        assert "currentConversationId = statsData.conversation_id" in content, (
            "应设置 currentConversationId"
        )

    def test_employee_history_loading_in_invoke_llm(self):
        """测试: _invoke_llm_employee 中加载对话历史逻辑存在且正确

        验证修复: @数字员工 LLM 调用能加载最近10条对话历史，
        而非仅发送 system + 当前用户消息。
        """
        import inspect
        from app.controllers.user_chat import UserEmployeeInvokeHandler

        # 读取 _invoke_llm_employee 方法源码
        source = inspect.getsource(UserEmployeeInvokeHandler._invoke_llm_employee)

        # 验证包含历史加载逻辑
        assert "get_recent_messages" in source, (
            "_invoke_llm_employee 应调用 get_recent_messages 加载历史"
        )
        assert "messages.extend(history_messages)" in source or \
            "messages.extend(history_messages)" in source, (
            "历史消息应通过 messages.extend 插入到 messages 数组中"
        )
        assert "history_messages" in source, (
            "应定义 history_messages 变量"
        )

        # 验证消息构建区域（messages = [] 之后）包含 history 加载和 extend
        msgs_start = source.find("messages = []")
        assert msgs_start > 0, "应包含 messages 初始化"
        msgs_section = source[msgs_start:]

        # 在 messages 构建区域中验证 history 在 user 消息之前
        hist_pos = msgs_section.find("history_messages")
        user_pos = msgs_section.find('"user"')
        assert hist_pos > 0, "messages 构建区域应包含 history_messages"
        assert user_pos > 0, "messages 构建区域应包含 user role"
        assert hist_pos < user_pos, (
            f"history_messages({hist_pos}) 应在 user({user_pos}) 之前插入 messages 数组"
        )

        # 验证 get_recent_messages 被调用且 limit=10
        assert "get_recent_messages(conv_id, limit=10)" in source, (
            "应使用 limit=10 调用 get_recent_messages"
        )

    def test_employee_post_ownership_validation(self):
        """测试: UserEmployeeInvokeHandler.post 包含会话归属校验

        验证修复: 数字员工路径的 conv_id 经过归属校验，
        防止跨用户访问对话历史。
        """
        import inspect
        from app.controllers.user_chat import UserEmployeeInvokeHandler

        source = inspect.getsource(UserEmployeeInvokeHandler.post)

        # 验证包含归属校验（中/英文注释均可）
        assert "conv.get(" in source, (
            "post 方法应查询 conv 记录进行归属校验"
        )
        assert "current_user" in source, (
            "post 方法应校验 conv.username 与 current_user 匹配"
        )
        # 验证校验失败时将 conv_id 置为 None
        assert "conv_id = None" in source, (
            "归属校验失败时应将 conv_id 置为 None"
        )

    def test_employee_message_save_is_async(self):
        """测试: _invoke_llm_employee 中消息保存使用 loop.run_in_executor

        验证: 与常规聊天路径一致，员工路径的消息保存也通过
        loop.run_in_executor 异步执行，避免阻塞 Tornado 事件循环。
        """
        import inspect
        from app.controllers.user_chat import UserEmployeeInvokeHandler

        source = inspect.getsource(UserEmployeeInvokeHandler._invoke_llm_employee)

        # 验证消息保存通过 loop.run_in_executor 异步执行
        # 不应直接调用 ConversationRepository.add_message 而不包裹
        save_section_start = source.find("# ── 保存对话消息 ──")
        assert save_section_start > 0, "应包含保存对话消息逻辑"

        save_section = source[save_section_start:]
        # 下一段代码块（在 write_audit_log 之前结束）
        audit_idx = save_section.find("write_audit_log")
        if audit_idx > 0:
            save_section = save_section[:audit_idx]

        # add_message 调用应被 loop.run_in_executor 包裹
        add_msg_count = save_section.count("add_message")
        executor_count = save_section.count("loop.run_in_executor")
        assert executor_count >= add_msg_count, (
            f"每条 add_message 调用应通过 loop.run_in_executor 异步执行，"
            f"发现 {add_msg_count} 处 add_message 但只有 {executor_count} 处 loop.run_in_executor"
        )
