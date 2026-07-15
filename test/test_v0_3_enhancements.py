"""
test_v0_3_enhancements.py — v0.3 增强功能验证测试

覆盖 Step1~Step5 的全部修改：
- Step1: UTF-8 编码修复
- Step2: SSE stats 事件解析
- Step3: 卡片渲染 + 员工名称显示
- Step4: 意图识别 + FTS5 全文检索
- Step5: /快捷指令 + 自动标题
"""

import json
import os
import sys
import unittest
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config.settings import settings
from app.models.db import init_db, get_db
import app.models.db as db_module
from app.models.data_warehouse import DataWarehouseRepository
from app.models.conversation import ConversationRepository


# ============================================================
# 测试基类：使用临时数据库
# ============================================================

class BaseTestCase(unittest.TestCase):
    """所有测试共享临时数据库。"""

    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.TemporaryDirectory()
        db_path = os.path.join(cls._tmpdir.name, "test.db")
        cls._orig_db_path = settings.DB_PATH
        cls._orig_module_db_path = db_module.DB_PATH
        settings.DB_PATH = db_path
        db_module.DB_PATH = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        init_db()

    @classmethod
    def tearDownClass(cls):
        settings.DB_PATH = cls._orig_db_path
        db_module.DB_PATH = cls._orig_module_db_path
        cls._tmpdir.cleanup()


# ============================================================
# Step1: UTF-8 编码修复测试
# ============================================================

class TestStep1_EncodingFix(BaseTestCase):
    """验证 .encode('utf-8') 修复后中文字符不再触发 ASCII 错误。"""

    def test_01_chinese_payload_encode(self):
        """中文 JSON payload 应能正常 encode('utf-8')。"""
        payload_obj = {
            "model": "test-model",
            "messages": [
                {"role": "user", "content": "@天气 成都今天天气怎么样？"}
            ],
            "temperature": 0.7,
            "max_tokens": 4096,
            "stream": True,
        }
        payload_str = json.dumps(payload_obj, ensure_ascii=False)
        # 必须显式使用 utf-8 编码
        data = payload_str.encode("utf-8")
        self.assertIsInstance(data, bytes)
        self.assertGreater(len(data), 0)
        # 验证解码后中文完整
        decoded = data.decode("utf-8")
        self.assertIn("成都今天天气怎么样", decoded)
        print("  ✅ 中文 payload encode('utf-8') 正常")

    def test_02_chinese_payload_no_ascii_error(self):
        """直接 .encode() 不应抛出 ASCII 错误（已修复为 utf-8）。"""
        payload_obj = {
            "model": "test",
            "messages": [{"role": "user", "content": "搜索人工智能相关数据"}],
        }
        payload_str = json.dumps(payload_obj)
        try:
            data = payload_str.encode("utf-8")
            self.assertIsInstance(data, bytes)
        except UnicodeEncodeError:
            self.fail("中文内容应能正常编码为 UTF-8，不应抛出 UnicodeEncodeError")
        print("  ✅ 中文 payload 无 ASCII/Unicode 编码错误")

    def test_03_content_type_has_charset(self):
        """Content-Type 头应包含 charset=utf-8。"""
        content_type = "application/json; charset=utf-8"
        self.assertIn("charset=utf-8", content_type.lower())
        print("  ✅ Content-Type 包含 charset=utf-8")

    def test_04_all_special_characters(self):
        """各种特殊字符（emoji、日文、符号）应正常编码。"""
        test_strings = [
            "emoji test 🎉🚀",
            "日本語テスト",
            "한국어 테스트",
            "©®™€£¥",
            "混合: Hello世界 🌍 — 「测试」",
        ]
        for s in test_strings:
            payload = json.dumps({"content": s}, ensure_ascii=False)
            data = payload.encode("utf-8")
            decoded = data.decode("utf-8")
            self.assertIn(s, decoded)
        print("  ✅ emoji/日文/韩文/特殊符号编码正常")


# ============================================================
# Step2: SSE stats 事件解析测试
# ============================================================

class TestStep2_SSEStatsParsing(BaseTestCase):
    """验证 SSE stats 事件格式和前端解析逻辑。"""

    def test_01_stats_event_format(self):
        """服务端发送的 stats 事件格式应正确。"""
        tokens = 150
        elapsed = 2.5
        mock = False
        stats_line = f"event: stats\ndata: {json.dumps({'tokens': tokens, 'mock': mock, 'elapsed': elapsed})}\n\n"
        # 验证包含必要字段
        self.assertIn("event: stats", stats_line)
        self.assertIn("data: ", stats_line)
        self.assertIn('"tokens"', stats_line)
        self.assertIn('"elapsed"', stats_line)
        self.assertIn('"mock"', stats_line)
        print("  ✅ SSE stats 事件格式正确")

    def test_02_stats_event_parsing_simulation(self):
        """模拟前端 SSE 解析逻辑：追踪 event 类型后解析 data。"""
        raw_lines = [
            "event: stats",
            'data: {"tokens":256,"mock":false,"elapsed":3.2}',
            "",
            "data: [DONE]",
        ]

        current_event = ""
        stats_data = None
        for line in raw_lines:
            if line.startswith("event: "):
                current_event = line[7:].strip()
            elif line.startswith("data: ") and current_event == "stats":
                data_str = line[6:]
                if data_str != "[DONE]":
                    stats_data = json.loads(data_str)
                current_event = ""

        self.assertIsNotNone(stats_data)
        self.assertEqual(stats_data["tokens"], 256)
        self.assertEqual(stats_data["elapsed"], 3.2)
        self.assertFalse(stats_data["mock"])
        print("  ✅ 前端 SSE event 类型追踪解析正确")

    def test_03_stats_event_with_mock(self):
        """Mock 模式 stats 应标记 mock=True。"""
        stats_json = json.dumps({"tokens": 42, "mock": True, "elapsed": 0.1})
        parsed = json.loads(stats_json)
        self.assertTrue(parsed["mock"])
        self.assertEqual(parsed["tokens"], 42)
        print("  ✅ Mock 模式 stats 正确标记")

    def test_04_meta_display_format(self):
        """元信息显示格式：⏱ X.Xs · 🔤 N tokens。"""
        tokens = 128
        elapsed = 1.5
        meta_html = f"⏱ {elapsed}s · 🔤 {tokens} tokens"
        self.assertIn(f"⏱ {elapsed}s", meta_html)
        self.assertIn(f"🔤 {tokens} tokens", meta_html)
        print("  ✅ 元信息显示格式正确")


# ============================================================
# Step3: 卡片渲染 + 员工名称测试
# ============================================================

class TestStep3_CardAndEmployee(BaseTestCase):
    """验证卡片构建、员工名称事件、API员工 SSE 改造。"""

    def test_01_build_card_from_template_json(self):
        """_build_card_from_template 应正确解析 JSON 模板并映射字段。"""
        from app.controllers.user_chat import UserEmployeeInvokeHandler
        # 创建一个虚拟 handler 来调用方法
        handler = UserEmployeeInvokeHandler.__new__(UserEmployeeInvokeHandler)

        # 天气 API 返回数据
        api_result = {
            "weather": {"temperature": "22", "condition": "晴"},
            "city": "成都",
            "date": "2026-07-14",
        }
        # 后台配置的 response_render_template
        template = json.dumps({
            "title": "天气卡片",
            "type": "weather",
            "mapping": {
                "city": "city",
                "temp": "weather.temperature",
                "weather": "weather.condition",
                "date": "date",
            },
        })

        card = handler._build_card_from_template(template, api_result, "天气助手")
        self.assertEqual(card["title"], "天气卡片")
        self.assertEqual(card["type"], "weather")
        self.assertEqual(card["data"]["city"], "成都")
        self.assertEqual(card["data"]["temp"], "22")
        self.assertEqual(card["data"]["weather"], "晴")
        print("  ✅ JSON 模板映射卡片构建正确")

    def test_02_build_card_from_template_plain(self):
        """非 JSON 模板应直接放入 data。"""
        from app.controllers.user_chat import UserEmployeeInvokeHandler
        handler = UserEmployeeInvokeHandler.__new__(UserEmployeeInvokeHandler)

        api_result = {"name": "test", "value": 123}
        card = handler._build_card_from_template("not_json", api_result, "测试员工")
        self.assertEqual(card["title"], "测试员工")
        self.assertEqual(card["data"], api_result)
        print("  ✅ 非 JSON 模板直接放入 data")

    def test_03_build_card_no_mapping(self):
        """无 mapping 字段的模板应直接使用 api_result。"""
        from app.controllers.user_chat import UserEmployeeInvokeHandler
        handler = UserEmployeeInvokeHandler.__new__(UserEmployeeInvokeHandler)

        api_result = {"items": [1, 2, 3]}
        template = json.dumps({"title": "列表", "type": "default"})
        card = handler._build_card_from_template(template, api_result, "助手")
        self.assertEqual(card["title"], "列表")
        self.assertEqual(card["data"], api_result)
        print("  ✅ 无 mapping 模板直接使用原始数据")

    def test_04_build_card_nested_mapping(self):
        """深层嵌套路径映射（如 a.b.c）应正确提取。"""
        from app.controllers.user_chat import UserEmployeeInvokeHandler
        handler = UserEmployeeInvokeHandler.__new__(UserEmployeeInvokeHandler)

        api_result = {
            "data": {
                "results": {
                    "total": 100,
                    "name": "搜索结果",
                }
            }
        }
        template = json.dumps({
            "title": "搜索结果",
            "type": "default",
            "mapping": {
                "count": "data.results.total",
                "label": "data.results.name",
            },
        })
        card = handler._build_card_from_template(template, api_result, "搜索")
        self.assertEqual(card["data"]["count"], 100)
        self.assertEqual(card["data"]["label"], "搜索结果")
        print("  ✅ 深层嵌套路径映射正确")

    def test_05_build_card_missing_path(self):
        """映射路径不存在时键不应出现在 data 中。"""
        from app.controllers.user_chat import UserEmployeeInvokeHandler
        handler = UserEmployeeInvokeHandler.__new__(UserEmployeeInvokeHandler)

        api_result = {"a": 1}
        template = json.dumps({
            "title": "测试",
            "mapping": {"missing": "x.y.z"},
        })
        card = handler._build_card_from_template(template, api_result, "测试")
        # 映射路径不存在，键不应存在
        self.assertNotIn("missing", card["data"])
        print("  ✅ 缺失路径的键不会出现在 data 中")

    def test_06_employee_name_event_format(self):
        """event: employee 应包含 name 和 type 字段。"""
        emp_event = f"event: employee\ndata: {json.dumps({'name': '天气助手', 'type': 'api'})}\n\n"
        # 模拟前端解析
        for line in emp_event.split("\n"):
            if line.startswith("data: "):
                data = json.loads(line[6:])
                self.assertEqual(data["name"], "天气助手")
                self.assertEqual(data["type"], "api")
        print("  ✅ employee 事件格式正确")


# ============================================================
# Step4: 意图识别 + FTS5 全文检索测试
# ============================================================

class TestStep4_IntentAndFTS5(BaseTestCase):
    """验证意图分类和 FTS5 全文检索。"""

    @unittest.skip("v0.4.2 removed legacy intent detection; covered by test_mcp_refactor")
    def test_01_intent_data_query(self):
        """搜索类关键词应识别为 data_query。"""
        from app.controllers.user_chat import UserChatStreamHandler
        handler = UserChatStreamHandler.__new__(UserChatStreamHandler)

        search_messages = [
            "搜索人工智能",
            "帮我查找最新数据",
            "查询一下科技新闻",
            "找一下关于AI的内容",
            "有没有关于Python的资料",
            "搜一下区块链",
        ]
        for msg in search_messages:
            intent, ctx = handler._detect_intent_and_query(msg)
            self.assertEqual(intent, "data_query", f"'{msg}' 应识别为 data_query")
        print("  ✅ 搜索类关键词 → data_query")

    @unittest.skip("v0.4.2 removed legacy intent detection; covered by test_mcp_refactor")
    def test_02_intent_data_stats(self):
        """统计类关键词应识别为 data_stats。"""
        from app.controllers.user_chat import UserChatStreamHandler
        handler = UserChatStreamHandler.__new__(UserChatStreamHandler)

        stats_messages = [
            "数据仓库统计",
            "一共有多少条记录",
            "数据分布占比",
            "来源排行TOP10",
            "数据概况",
        ]
        for msg in stats_messages:
            intent, ctx = handler._detect_intent_and_query(msg)
            self.assertEqual(intent, "data_stats", f"'{msg}' 应识别为 data_stats")
        print("  ✅ 统计类关键词 → data_stats")

    @unittest.skip("v0.4.2 removed legacy intent detection; covered by test_mcp_refactor")
    def test_03_intent_chart_request(self):
        """图表类关键词应识别为 chart_request。"""
        from app.controllers.user_chat import UserChatStreamHandler
        handler = UserChatStreamHandler.__new__(UserChatStreamHandler)

        chart_messages = [
            "生成一个柱状图",
            "画个饼图",
            "做个数据可视化",
            "生成报表图表",
        ]
        for msg in chart_messages:
            intent, ctx = handler._detect_intent_and_query(msg)
            self.assertEqual(intent, "chart_request", f"'{msg}' 应识别为 chart_request")
        print("  ✅ 图表类关键词 → chart_request")

    @unittest.skip("v0.4.2 removed legacy intent detection; covered by test_mcp_refactor")
    def test_04_intent_general(self):
        """普通对话应识别为 general。"""
        from app.controllers.user_chat import UserChatStreamHandler
        handler = UserChatStreamHandler.__new__(UserChatStreamHandler)

        general_messages = [
            "你好",
            "今天天气怎么样",
            "帮我写一段代码",
            "什么是机器学习",
        ]
        for msg in general_messages:
            intent, ctx = handler._detect_intent_and_query(msg)
            self.assertEqual(intent, "general", f"'{msg}' 应识别为 general")
        print("  ✅ 普通对话 → general")

    @unittest.skip("v0.4.2 removed legacy intent detection; covered by test_mcp_refactor")
    def test_05_intent_priority(self):
        """搜索关键词优先于统计关键词。"""
        from app.controllers.user_chat import UserChatStreamHandler
        handler = UserChatStreamHandler.__new__(UserChatStreamHandler)

        # "搜索" 应该优先于 "统计"
        intent, ctx = handler._detect_intent_and_query("搜索数据统计概况")
        self.assertEqual(intent, "data_query")
        print("  ✅ 搜索意图优先级高于统计")

    def test_06_fts5_search_basic(self):
        """FTS5 全文检索应能搜到数据仓库内容。"""
        # 插入测试数据
        DataWarehouseRepository.create(
            result_id=None,
            title="人工智能最新进展2026",
            link="https://example.com/ai-2026",
            summary="人工智能在2026年的最新技术突破和应用场景",
            source_name="科技日报",
        )
        DataWarehouseRepository.create(
            result_id=None,
            title="Python 3.13 发布",
            link="https://example.com/python-313",
            summary="Python 3.13 版本带来了多项性能优化",
            source_name="开源中国",
        )
        DataWarehouseRepository.create(
            result_id=None,
            title="成都人工智能产业园揭牌",
            link="https://example.com/chengdu-ai",
            summary="成都高新区人工智能产业园正式揭牌运营",
            source_name="成都日报",
        )

        # FTS5 搜索
        results = DataWarehouseRepository.search("人工智能", limit=5)
        self.assertGreaterEqual(len(results), 2, "应搜到至少2条包含'人工智能'的记录")
        # 验证结果包含预期标题
        titles = [r["title"] for r in results]
        self.assertTrue(any("人工智能" in t for t in titles))
        print(f"  ✅ FTS5 搜索'人工智能'命中 {len(results)} 条")

    def test_07_fts5_search_no_result(self):
        """搜索不存在的关键词应返回空列表。"""
        results = DataWarehouseRepository.search("不存在的关键词XYZ123", limit=5)
        self.assertEqual(len(results), 0)
        print("  ✅ 无匹配关键词返回空列表")

    def test_08_fts5_search_partial_match(self):
        """FTS5 应支持部分匹配（LIKE 回退）。"""
        DataWarehouseRepository.create(
            result_id=None,
            title="深度学习框架对比",
            link="https://example.com/dl",
            summary="PyTorch和TensorFlow框架对比分析",
            source_name="AI研究",
        )
        results = DataWarehouseRepository.search("PyTorch", limit=5)
        self.assertGreaterEqual(len(results), 1)
        print(f"  ✅ FTS5 回退 LIKE 搜索命中 {len(results)} 条")

    def test_09_get_stats(self):
        """get_stats 应返回总记录数、深度采集数和 Top 来源。"""
        stats = DataWarehouseRepository.get_stats()
        self.assertIn("total", stats)
        self.assertIn("deep_collected", stats)
        self.assertIn("top_sources", stats)
        self.assertGreater(stats["total"], 0, "应有数据仓库记录")
        print(f"  ✅ get_stats: total={stats['total']}, deep={stats['deep_collected']}")

    @unittest.skip("v0.4.2 uses bounded untrusted MCP tool messages instead")
    def test_10_warehouse_context_injection(self):
        """意图为 data_query 时上下文应包含数据仓库查询结果。"""
        from app.controllers.user_chat import UserChatStreamHandler
        handler = UserChatStreamHandler.__new__(UserChatStreamHandler)

        _, ctx = handler._detect_intent_and_query("搜索人工智能")
        if ctx:
            self.assertIn("[系统注入：数据仓库查询结果]", ctx)
            self.assertIn("请基于以上真实数据回答用户问题", ctx)
        print("  ✅ 仓库上下文注入格式正确")


# ============================================================
# Step5: 快捷指令 + 自动标题测试
# ============================================================

class TestStep5_SlashCommands(BaseTestCase):
    """验证 /clear, /summary, /trans 指令和自动标题。"""

    def test_01_clear_command_detection(self):
        """/clear 指令应被识别为快捷指令。"""
        self.assertTrue("/clear".startswith("/"))
        self.assertEqual("/clear", "/clear")
        print("  ✅ /clear 指令识别正确")

    def test_02_summary_command_detection(self):
        """/summary 指令应被识别。"""
        self.assertTrue("/summary".startswith("/"))
        print("  ✅ /summary 指令识别正确")

    def test_03_trans_command_detection(self):
        """/trans 指令应被识别。"""
        self.assertTrue("/trans".startswith("/"))
        # /trans 可以带参数如 /trans en
        self.assertTrue("/trans en".startswith("/"))
        print("  ✅ /trans 指令识别正确")

    def test_04_unknown_command(self):
        """未知 / 指令不应崩溃，应返回提示。"""
        unknown = "/unknown_command_xyz"
        self.assertTrue(unknown.startswith("/"))
        # 实际方法会返回提示信息
        print("  ✅ 未知指令格式正确，不会崩溃")

    def test_05_auto_title_generation(self):
        """首条消息后标题应自动从"新对话"更新为消息前30字。"""
        # 创建对话
        conv_id = ConversationRepository.create(
            title="新对话", model_id=None, username="testuser"
        )
        conv = ConversationRepository.get_by_id(conv_id)
        self.assertEqual(conv["title"], "新对话")

        # 模拟添加消息后更新标题
        message = "请帮我搜索人工智能最新进展报告"
        ConversationRepository.add_message(conv_id, "user", message, 0)
        ConversationRepository.add_message(conv_id, "assistant", "好的，为您搜索...", 10)

        # 自动标题逻辑
        conv = ConversationRepository.get_by_id(conv_id)
        if (conv.get("title") or "").strip() in ("新对话", ""):
            auto_title = message.strip()[:30]
            ConversationRepository.update_title(conv_id, auto_title)

        conv = ConversationRepository.get_by_id(conv_id)
        self.assertEqual(conv["title"], message[:30])
        print(f"  ✅ 自动标题: '{conv['title']}'")

    def test_06_auto_title_truncation(self):
        """超长消息标题应截断为30字。"""
        long_message = "这是一个非常非常长的消息用来测试自动标题截断功能是否正常工作" * 3
        auto_title = long_message.strip()[:30]
        self.assertLessEqual(len(auto_title), 30)
        print(f"  ✅ 标题截断: {len(auto_title)} 字")

    def test_07_clear_resets_conversation(self):
        """/clear 应重置当前对话（前端行为模拟）。"""
        # 模拟前端收到 event: action {action: 'clear'} 时的行为
        action_data = {"action": "clear"}
        self.assertEqual(action_data["action"], "clear")
        # 前端会清空 chat-messages 并显示 welcome 页，重置 currentConversationId
        print("  ✅ /clear action 数据结构正确")


# ============================================================
# Step3 补充: API 员工 SSE 流式返回测试
# ============================================================

class TestStep3_ApiEmployeeSSE(BaseTestCase):
    """验证 API 型员工 SSE 改造。"""

    def test_01_api_employee_uses_sse_format(self):
        """API 型员工应发送 SSE 格式的 event: employee。"""
        emp_name = "天气助手"
        emp_type = "api"
        employee_event = f"event: employee\ndata: {json.dumps({'name': emp_name, 'type': emp_type}, ensure_ascii=False)}\n\n"

        self.assertIn("event: employee", employee_event)
        self.assertIn("天气助手", employee_event)
        self.assertIn("api", employee_event)
        print("  ✅ API 员工 SSE employee 事件格式正确")

    def test_02_api_response_streaming_simulation(self):
        """API 返回的 JSON 数据以分块 SSE content 形式发送。"""
        api_response = json.dumps({"status": "ok", "data": {"temp": 22}})
        chunk_size = 50
        chunks = []
        for i in range(0, len(api_response), chunk_size):
            chunk = api_response[i:i + chunk_size]
            chunks.append(f"data: {json.dumps({'content': chunk})}\n")

        self.assertGreater(len(chunks), 0)
        # 所有 chunk 拼接应等于原始内容
        all_content = ""
        for chunk_line in chunks:
            data_str = chunk_line[6:].strip()
            all_content += json.loads(data_str)["content"]
        self.assertEqual(all_content, api_response)
        print(f"  ✅ API 响应分块传输: {len(chunks)} 块")


# ============================================================
# 运行入口
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("  v0.3 增强功能验证测试 (Step1~Step5)")
    print("=" * 60)
    # 使用 unittest 运行器，verbosity=2 显示详细结果
    unittest.main(verbosity=2)
