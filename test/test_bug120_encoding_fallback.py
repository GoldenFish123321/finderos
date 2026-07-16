"""
test_bug120_encoding_fallback.py — Issue #120: deep_collector 编码探测缺少容错回退

验证两阶段编码探测策略：
1. strict 模式试探 → 检测真实编码
2. errors="replace" 容错解码 → 防止非法字节导致崩溃
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.deep_collector import deep_fetch


class TestIssue120_EncodingFallback(unittest.TestCase):
    """Issue #120: 编码探测 errors="replace" 容错测试"""

    @staticmethod
    def _mock_response(body_bytes, status=200, encoding=""):
        """创建模拟的 HTTP 响应对象。"""
        class FakeHeaders(dict):
            def get(self, key, default=""):
                return dict.__getitem__(self, key) if key in self else default

        class FakeResponse:
            def __init__(self):
                self.status = status
                self.body = body_bytes
                self.headers = FakeHeaders({"Content-Encoding": encoding})
        return FakeResponse()

    # ── 编码正确性测试 ─────────────────────────────────────────

    def test_01_pure_utf8_detected_and_preserved(self):
        """纯 UTF-8 中文页面：应正确检测为 UTF-8 并保留中文标题。"""
        title_cn = "测试页面标题"
        title_bytes = title_cn.encode("utf-8")
        body_cn = "这是正文内容。"
        body_bytes = body_cn.encode("utf-8")
        html = (
            b"<html><head><title>" + title_bytes + b"</title></head>"
            b"<body><article><p>" + body_bytes * 200 +
            b"</p></article></body></html>"
        )
        mock_resp = self._mock_response(html)

        with patch("app.services.deep_collector.safe_http_request", return_value=mock_resp):
            with patch("app.services.deep_collector.validate_url_safe", return_value=(True, "", "")):
                status, title, content, error = deep_fetch("http://example.com/utf8")
                self.assertEqual(status, 200, f"应返回200，实际: {status}")
                self.assertEqual(error, "", f"不应有错误，实际: {error}")
                self.assertIn(title_cn, title,
                              f"UTF-8 标题应正确解码，期望含 '{title_cn}'，实际: '{title}'")
                # 正文不应有大量替换字符
                replacement_count = content.count("\ufffd")
                self.assertEqual(replacement_count, 0,
                                 f"UTF-8 正文不应含替换字符，实际 {replacement_count} 个")
                print("  ✅ 纯 UTF-8 中文页面正确解码")

    def test_02_pure_gbk_detected_correctly(self):
        """纯 GBK 中文页面：应正确检测为 GBK（而非 UTF-8 误解码）。"""
        # GBK 编码的中文页面
        title_cn = "测试页面"
        title_gbk = title_cn.encode("gbk")
        content_cn = "中文正文内容测试"
        content_gbk = content_cn.encode("gbk")

        html = (
            b"<html><head><title>" + title_gbk + b"</title></head>"
            b"<body><article><p>" + content_gbk * 100 +
            b"</p></article></body></html>"
        )
        mock_resp = self._mock_response(html)

        with patch("app.services.deep_collector.safe_http_request", return_value=mock_resp):
            with patch("app.services.deep_collector.validate_url_safe", return_value=(True, "", "")):
                status, title, content, error = deep_fetch("http://example.com/gbk")
                self.assertEqual(status, 200, f"应返回200，实际: {status}")
                self.assertEqual(error, "", f"不应有错误，实际: {error}")
                # GBK 编码的中文标题应被正确解码
                self.assertIn(title_cn, title,
                              f"GBK 标题应正确解码为 '{title_cn}'，实际: '{title}'")
                # 确认不是 UTF-8 误解码的乱码
                self.assertNotIn("娴嬭瘯", title,
                                 f"不应出现 UTF-8 误解码乱码，实际标题: '{title}'")
                # 正文不应有大量替换字符
                replacement_count = content.count("\ufffd")
                self.assertLess(replacement_count, 5,
                                f"GBK 正文替换字符应极少，实际 {replacement_count} 个")
                print("  ✅ 纯 GBK 页面正确检测并解码")

    # ── 容错回退测试 ───────────────────────────────────────────

    def test_03_utf8_with_trailing_garbage_no_crash(self):
        """UTF-8 页面 + 尾部非法字节：strict 模式探测失败 → 回退到 latin-1 → 不崩溃。"""
        title_bytes = "Normal Page".encode("utf-8")
        valid_html = (
            b"<html><head><title>" + title_bytes + b"</title></head>"
            b"<body><p>" + b"Hello World! " * 200 + b"</p></body></html>"
        )
        # 尾部追加非法字节（对所有编码均为非法）
        bad_bytes = valid_html + b"\xff\xfe\x00\x01\x80\x81\x90\xff"

        mock_resp = self._mock_response(bad_bytes)

        with patch("app.services.deep_collector.safe_http_request", return_value=mock_resp):
            with patch("app.services.deep_collector.validate_url_safe", return_value=(True, "", "")):
                status, title, content, error = deep_fetch("http://example.com/garbage")
                self.assertNotIn("UnicodeDecodeError", error,
                                 f"不应抛出解码错误，实际: {error}")
                self.assertNotIn("codec can't decode", error,
                                 f"不应有编码错误，实际: {error}")
                print("  ✅ UTF-8+尾部垃圾字节无崩溃（回退到 latin-1）")

    def test_04_all_illegal_bytes_no_crash(self):
        """全部非法字节：无编码匹配 strict 模式 → utf-8 replace 兜底 → 不崩溃。"""
        all_bad = b"\xff\xfe\x00\x01\x80\x81\x90\xff" * 100

        mock_resp = self._mock_response(all_bad)

        with patch("app.services.deep_collector.safe_http_request", return_value=mock_resp):
            with patch("app.services.deep_collector.validate_url_safe", return_value=(True, "", "")):
                status, title, content, error = deep_fetch("http://example.com/allbad")
                self.assertNotIn("UnicodeDecodeError", error,
                                 f"不应抛出解码错误，实际: {error}")
                # 会因内容过短而返回错误（预期行为，不是崩溃）
                print("  ✅ 全部非法字节兜底不崩溃")

    def test_05_latin1_as_final_fallback(self):
        """latin-1 是最后候选编码，对所有 256 个字节值均合法。"""
        all_bytes = bytes(range(256)) * 50  # 约 12KB
        prefix = b"<html><head><title>Binary Page</title></head><body><p>"
        suffix = b"</p></body></html>"
        data = prefix + all_bytes + b" " * 10000 + suffix

        mock_resp = self._mock_response(data)

        with patch("app.services.deep_collector.safe_http_request", return_value=mock_resp):
            with patch("app.services.deep_collector.validate_url_safe", return_value=(True, "", "")):
                status, title, content, error = deep_fetch("http://example.com/latin1")
                self.assertNotIn("UnicodeDecodeError", error,
                                 f"不应抛出解码错误，实际: {error}")
                # latin-1 strict 模式对所有字节均能解码
                self.assertIn("Binary Page", title)
                print("  ✅ latin-1 后备编码对所有字节均安全")

    def test_06_gbk_with_minor_corruption_no_crash(self):
        """GBK 页面含少量非法字节：GBK strict 失败但其他编码回退 → 不崩溃。"""
        # GBK 编码中文 + 少量非法字节
        title_gbk = "新闻标题".encode("gbk")
        body_gbk = "新闻正文内容".encode("gbk")
        html = (
            b"<html><head><title>" + title_gbk + b"</title></head>"
            b"<body><article><p>" + body_gbk * 100 +
            b"</p></article></body></html>"
        )
        # 在中间插入非法字节（\x80 在 GBK 中非法）
        corrupted = html[:50] + b"\x80\x81" + html[50:]

        mock_resp = self._mock_response(corrupted)

        with patch("app.services.deep_collector.safe_http_request", return_value=mock_resp):
            with patch("app.services.deep_collector.validate_url_safe", return_value=(True, "", "")):
                status, title, content, error = deep_fetch("http://example.com/gbk_corrupt")
                self.assertNotIn("UnicodeDecodeError", error,
                                 f"不应抛出解码错误，实际: {error}")
                print("  ✅ GBK+少量损坏字节不崩溃")


if __name__ == "__main__":
    unittest.main(verbosity=2)
