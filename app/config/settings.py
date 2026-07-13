"""
settings.py — 应用配置管理中心

所有配置支持环境变量覆盖，适用于开发/测试/生产环境切换。
"""

import os


class Settings:
    """全局应用配置"""

    # === 安全配置 ===
    COOKIE_SECRET = os.environ.get("COOKIE_SECRET", "")
    """Tornado 安全 Cookie 签名密钥。生产环境必须通过环境变量注入。"""

    DEBUG = os.environ.get("DEBUG", "").lower() == "true"
    """调试模式。默认关闭，不会在前端暴露堆栈跟踪。"""

    XSRF_COOKIES = True
    """全局启用 XSRF 防护。"""

    LOGIN_URL = "/"
    """未登录时的跳转地址。"""

    # === 数据库配置 ===
    DB_PATH = os.environ.get("DB_PATH", "database/finderos.db")
    """SQLite 数据库文件路径。"""

    # === 密码学配置 ===
    PBKDF2_ITERATIONS = int(os.environ.get("PBKDF2_ITERATIONS", 600_000))
    """PBKDF2-SHA256 迭代次数。OWASP 2023 推荐 ≥ 600,000。"""

    # === 网络配置 ===
    PORT = int(os.environ.get("PORT", 10010))
    """HTTP 服务监听端口。"""

    # === 功能配置 ===
    PAGE_SIZE = int(os.environ.get("PAGE_SIZE", 20))
    """列表分页大小。"""

    LOGIN_MAX_FAILURES = int(os.environ.get("LOGIN_MAX_FAILURES", 5))
    """登录失败次数上限（同一 IP + 用户名）。"""

    LOGIN_LOCKOUT_SECONDS = int(os.environ.get("LOGIN_LOCKOUT_SECONDS", 900))
    """登录锁定时间（秒），默认 15 分钟。"""


settings = Settings()
