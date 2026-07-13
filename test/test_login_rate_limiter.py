"""
test_login_rate_limiter.py — 登录限速器单元测试

测试 LoginRateLimiter 的检查、记录、清除逻辑。
"""
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.controllers.auth import LoginRateLimiter
from app.config.settings import settings


class TestLoginRateLimiter(unittest.TestCase):
    """登录限速器测试"""

    def setUp(self):
        """每个测试使用独立的限速器实例。"""
        self.limiter = LoginRateLimiter(scope="test")

    def test_initial_check_passes(self):
        """初始状态允许登录。"""
        ok, msg = self.limiter.check("1.2.3.4", "admin")
        self.assertTrue(ok)
        self.assertEqual(msg, "")

    def test_record_and_check(self):
        """记录一次失败后仍允许登录（未达阈值）。"""
        self.limiter.record_failure("1.2.3.4", "user1")
        ok, _ = self.limiter.check("1.2.3.4", "user1")
        self.assertTrue(ok)

    def test_locked_after_max_failures(self):
        """达到最大失败次数后被锁定。"""
        ip, username = "10.0.0.1", "lockeduser"
        for _ in range(settings.LOGIN_MAX_FAILURES):
            self.limiter.record_failure(ip, username)
        ok, msg = self.limiter.check(ip, username)
        self.assertFalse(ok)
        self.assertIn("秒后再试", msg)

    def test_clear_after_success(self):
        """登录成功后清除记录。"""
        ip, username = "10.0.0.2", "gooduser"
        for _ in range(3):
            self.limiter.record_failure(ip, username)
        self.limiter.clear(ip, username)
        ok, _ = self.limiter.check(ip, username)
        self.assertTrue(ok)

    def test_different_users_independent(self):
        """不同用户的失败计数相互独立。"""
        self.limiter.record_failure("1.1.1.1", "userA")
        self.limiter.record_failure("1.1.1.1", "userA")
        ok, _ = self.limiter.check("1.1.1.1", "userB")
        self.assertTrue(ok)  # userB 不受 userA 影响

    def test_different_ips_independent(self):
        """不同 IP 的失败计数相互独立。"""
        self.limiter.record_failure("1.1.1.1", "sameuser")
        self.limiter.record_failure("1.1.1.1", "sameuser")
        ok, _ = self.limiter.check("2.2.2.2", "sameuser")
        self.assertTrue(ok)  # 不同 IP，计数独立

    def test_separate_scopes(self):
        """不同作用域的限速器相互独立。"""
        limiter2 = LoginRateLimiter(scope="admin")
        ip, username = "3.3.3.3", "admin"
        for _ in range(settings.LOGIN_MAX_FAILURES):
            self.limiter.record_failure(ip, username)
        ok, _ = limiter2.check(ip, username)
        self.assertTrue(ok)  # 不同 scope 独立


if __name__ == "__main__":
    unittest.main()
