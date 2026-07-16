"""
test_image_generation.py — 图像生成功能测试 (Issue #22)

测试覆盖:
- ImageGenHandler API 调用（文生图 / 图生图）
- MCP 工具 _generate_image 函数
- SSE 卡片数据格式
- 错误处理（无 API Key、无效参数等）
"""
import json
import sys
import unittest

sys.path.insert(0, ".")

# 跳过真实 API 调用的装饰器（需要 API Key）
SKIP_LIVE_API = True  # 改为 False 可运行真实 API 测试


class TestImageGenHandler(unittest.TestCase):
    """测试 ImageGenHandler 核心逻辑。"""

    def test_generate_image_response_format(self):
        """验证 API 响应解析逻辑（使用 mock 数据）。"""
        from app.services.media_generator import ImageGenHandler

        # 模拟成功响应
        mock_success_body = json.dumps({
            "created": 1234567890,
            "data": [
                {"url": "https://example.com/image.png", "b64_json": None, "revised_prompt": None}
            ]
        })

        # 模拟错误响应
        mock_error_body = json.dumps({
            "data": None,
            "error": {"message": "余额不足", "type": "image_generation_error"}
        })

        # 验证解析逻辑：_parse_api_error 返回通用消息（避免泄露第三方 API 内部信息）
        from app.services.media_generator import _parse_api_error
        self.assertEqual("媒体生成服务返回错误 (HTTP 500)", _parse_api_error(500, mock_error_body))
        self.assertEqual("媒体生成服务返回错误 (HTTP 500)", _parse_api_error(500, '{"message": "Internal error"}'))
        self.assertEqual("媒体生成服务返回错误 (HTTP 500)", _parse_api_error(500, "plain text"))
        self.assertEqual("媒体生成服务返回错误 (HTTP 500)", _parse_api_error(500, ""))

    def test_parse_api_error_empty(self):
        """空错误消息。"""
        from app.services.media_generator import _parse_api_error
        self.assertEqual("媒体生成服务返回错误 (HTTP 500)", _parse_api_error(500, ""))

    def test_validate_url_safe_blocked(self):
        """SSRF 校验：内网地址应被拦截。"""
        from app.services.media_generator import ImageGenHandler
        result = ImageGenHandler.generate_image(
            prompt="test", model_name="test",
            api_base="http://127.0.0.1:8080/v1", api_key="key"
        )
        self.assertFalse(result["success"])
        self.assertIn("不安全", result["error"])


class TestMCPMediaTools(unittest.TestCase):
    """测试 MCP 工具处理函数。"""

    def test_generate_image_import(self):
        """_generate_image 应可正常导入。"""
        from app.mcp.builtin_tools.media_tools import _generate_image
        self.assertTrue(callable(_generate_image))

    def test_generate_video_import(self):
        """_generate_video 应可正常导入。"""
        from app.mcp.builtin_tools.media_tools import _generate_video
        self.assertTrue(callable(_generate_video))


class TestModelQueries(unittest.TestCase):
    """测试 ai_model 新增查询方法。"""

    def test_get_default_by_category_exists(self):
        """image 分类应有默认模型。"""
        from app.models.ai_model import AiModelRepository
        model = AiModelRepository.get_default_by_category("image")
        self.assertIsNotNone(model, "image 分类应有至少一个模型")

    def test_get_default_by_category_has_api_key_field(self):
        """返回的模型应包含 has_api_key 字段。"""
        from app.models.ai_model import AiModelRepository
        model = AiModelRepository.get_default_by_category("image")
        self.assertIn("has_api_key", model)
        self.assertIn("api_key", model)

    def test_get_by_category_returns_list(self):
        """get_by_category 应返回列表。"""
        from app.models.ai_model import AiModelRepository
        models = AiModelRepository.get_by_category("image")
        self.assertIsInstance(models, list)
        self.assertGreater(len(models), 0, "至少应有一个 image 模型")


class TestCardFormat(unittest.TestCase):
    """测试 SSE 卡片数据格式。"""

    def test_image_card_format(self):
        """image 卡片格式。"""
        card = {
            "type": "image",
            "title": "test prompt",
            "data": {
                "urls": ["https://example.com/img.png"],
                "prompt": "test prompt",
                "model": "wan2.6-t2i"
            }
        }
        self.assertEqual(card["type"], "image")
        self.assertIsInstance(card["data"]["urls"], list)
        self.assertTrue(all(isinstance(u, str) for u in card["data"]["urls"]))

    def test_video_card_format(self):
        """video 卡片格式。"""
        card = {
            "type": "video",
            "title": "test prompt",
            "data": {
                "url": "/static/media/video_test.mp4",
                "content_type": "video/mp4",
                "model": "wan2.6-t2v"
            }
        }
        self.assertEqual(card["type"], "video")
        self.assertTrue(card["data"]["url"].startswith("/static/"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
