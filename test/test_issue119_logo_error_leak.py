"""
test_issue119_logo_error_leak.py — 测试 Logo 上传失败时不会泄露异常信息到 URL。

Issue #119: admin_config.py Logo上传失败时异常消息通过URL参数泄露内部信息。
修复后：URL 中应为通用错误消息，详细错误仅记录到日志。

注意：本测试直接解析源码文件，避免导入 tornado 依赖。
"""
import os
import re
import unittest


HERE = os.path.dirname(os.path.abspath(__file__))
ADMIN_CONFIG = os.path.join(HERE, "..", "app", "controllers", "admin_config.py")


def _read_src():
    with open(os.path.normpath(ADMIN_CONFIG), "r", encoding="utf-8") as f:
        return f.read()


class TestIssue119LogoErrorLeak(unittest.TestCase):
    """验证 Logo 上传异常处理代码不泄露内部信息。"""

    @classmethod
    def setUpClass(cls):
        cls.src = _read_src()

    def test_logging_import_exists(self):
        """修复后应导入 logging 模块。"""
        self.assertIn("import logging", self.src,
                      "should import logging module")

    def test_logger_defined(self):
        """修复后应有模块级 logger。"""
        self.assertIn("logger = logging.getLogger", self.src,
                      "should define module-level logger")

    def test_logger_error_in_except_block(self):
        """except 块中应调用 logger.error 记录异常详情。"""
        self.assertIn("logger.error", self.src,
                      "should call logger.error in exception handler")

    def test_redirect_uses_generic_message_not_raw_exception(self):
        """redirect URL 不应包含 str(e) 或 f-string 异常变量。"""
        # 查找所有 redirect 调用
        redirect_lines = re.findall(r'self\.redirect\([^)]+\)', self.src)
        for line in redirect_lines:
            # 不应包含原始异常变量展开
            self.assertNotIn('{e}', line,
                             f"Redirect URL should not contain raw {{e}}: {line}")
            self.assertNotIn('str(e)', line,
                             f"Redirect URL should not contain str(e): {line}")

    def test_no_filesystem_paths_in_redirect_urls(self):
        """redirect URL 的 error 参数中不应包含文件系统路径。"""
        redirect_lines = re.findall(r'self\.redirect\([^)]+\)', self.src)
        for line in redirect_lines:
            if 'error=' in line:
                self.assertNotIn('/app/', line,
                                 f"No filesystem path in redirect: {line}")
                self.assertNotIn('.py', line)

    def test_generic_error_message_present(self):
        """except 块的 redirect 应使用通用中文错误消息。"""
        self.assertIn('Logo 上传失败', self.src,
                      "should contain generic Chinese 'Logo 上传失败' message")

    def test_no_exception_class_names_in_redirects(self):
        """redirect URL 不应包含 Python 异常类名。"""
        redirect_lines = re.findall(r'self\.redirect\([^)]+\)', self.src)
        exception_names = ['Exception', 'Error:', 'Traceback',
                           'OSError', 'IOError', 'PermissionError',
                           'AttributeError', 'TypeError', 'ValueError']
        for line in redirect_lines:
            for exc in exception_names:
                self.assertNotIn(exc, line,
                                 f"Exception name '{exc}' should not be in redirect: {line}")


if __name__ == "__main__":
    unittest.main()
