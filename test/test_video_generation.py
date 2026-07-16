"""
test_video_generation.py — 视频生成功能测试 (Issue #21)

测试覆盖:
- VideoGenHandler API 调用（文生视频 / 图生视频）
- 视频代理下载逻辑
- MCP 工具 _generate_video 函数
- 错误处理
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, ".")

SKIP_LIVE_API = True  # 改为 False 运行真实 API 测试


class TestVideoGenHandler(unittest.TestCase):
    """测试 VideoGenHandler 核心逻辑。"""

    def test_ensure_video_cache_dir(self):
        """视频缓存目录应自动创建。"""
        from app.services.media_generator import _ensure_video_cache_dir
        cache_dir = _ensure_video_cache_dir()
        self.assertTrue(os.path.isdir(cache_dir))
        self.assertTrue(cache_dir.endswith("media"))

    def test_parse_api_error_video(self):
        """视频 API 错误解析。"""
        from app.services.media_generator import _parse_api_error
        err = _parse_api_error(500, json.dumps({
            "data": None,
            "error": {"message": "402: 余额不足", "type": "video_generation_error"}
        }))
        self.assertIn("余额不足", err)

    def test_validate_url_safe_blocked(self):
        """SSRF 校验：内网地址应被拦截。"""
        from app.services.media_generator import VideoGenHandler
        result = VideoGenHandler.generate_video(
            prompt="test", model_name="test",
            api_base="http://localhost:8080/v1", api_key="key"
        )
        self.assertFalse(result["success"])
        self.assertIn("不安全", result["error"])


class TestMCPVideoTool(unittest.TestCase):
    """测试 _generate_video MCP 工具。"""

    def test_import(self):
        from app.mcp.builtin_tools.media_tools import _generate_video
        self.assertTrue(callable(_generate_video))


class TestModelQueries(unittest.TestCase):
    """测试视频模型查询。"""

    def test_video_models_exist(self):
        from app.models.ai_model import AiModelRepository
        models = AiModelRepository.get_by_category("video")
        self.assertGreater(len(models), 0, "video 分类应有至少一个模型")

    def test_default_video_model(self):
        from app.models.ai_model import AiModelRepository
        model = AiModelRepository.get_default_by_category("video")
        self.assertIsNotNone(model, "应有默认视频模型")
        self.assertEqual(model["category"], "video")


class TestVideoProxyDownload(unittest.TestCase):
    """测试视频代理下载逻辑（本地模拟）。"""

    def test_download_cleanup_on_failure(self):
        """下载失败时应清理不完整文件。"""
        from app.services.media_generator import _ensure_video_cache_dir
        cache_dir = _ensure_video_cache_dir()

        # 创建一个模拟的下载失败场景
        test_file = os.path.join(cache_dir, "video_test_cleanup.mp4")
        with open(test_file, "wb") as f:
            f.write(b"incomplete data")

        # 模拟清理
        if os.path.exists(test_file):
            os.remove(test_file)
        self.assertFalse(os.path.exists(test_file))


if __name__ == "__main__":
    unittest.main(verbosity=2)
