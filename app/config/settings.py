"""
settings.py — 应用配置管理中心

所有配置支持环境变量覆盖，适用于开发/测试/生产环境切换。
"""

import os


class Settings:
    """全局应用配置"""

    # === 应用版本（唯一硬编码位置） ===
    VERSION = "1.0.2-beta"
    """应用版本号。项目中所有版本展示均由此处统一管理。"""

    # === 安全配置 ===
    COOKIE_SECRET = os.environ.get("COOKIE_SECRET", "")
    """Tornado 安全 Cookie 签名密钥。生产环境必须通过环境变量注入。"""

    DEBUG = os.environ.get("DEBUG", "").lower() == "true"
    """调试模式。默认关闭，不会在前端暴露堆栈跟踪。"""

    XSRF_COOKIES = True
    """全局启用 XSRF 防护。"""

    LOGIN_URL = "/"
    """未登录时的跳转地址。"""

    # === 安全响应头 ===
    SECURITY_HEADERS = {
        "X-Frame-Options": "DENY",
        "X-Content-Type-Options": "nosniff",
        "X-XSS-Protection": "1; mode=block",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        # 严格化 CSP（借鉴陈子墨）：移除 unsafe-eval，收窄 connect-src，增加 frame-ancestors/base-uri/form-action
        "Content-Security-Policy": (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data: https:; "
            "font-src 'self' https://cdn.jsdelivr.net; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        ),
    }
    """HTTP 安全响应头集合（CSP / X-Frame / HSTS 等 OWASP 推荐头）。"""

    # === SSRF 防护 ===
    SSRF_BLOCKED_HOSTS = [
        "127.0.0.1", "localhost", "0.0.0.0", "::1",
        "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
        "169.254.0.0/16", "100.64.0.0/10",
    ]
    """SSRF 防护：禁止请求的内网/回环地址段。"""

    SSRF_ALLOWED_SCHEMES = {"http", "https"}
    """SSRF 防护：仅允许的 URL 协议。"""

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

    AUDIT_ENABLED = os.environ.get("AUDIT_ENABLED", "").lower() != "false"
    """是否启用审计日志（默认启用）。"""

    # === 定时采集配置 ===
    SCHEDULED_COLLECT_KEYWORDS: list[str] = [
        kw.strip() for kw in os.environ.get(
            "SCHEDULED_COLLECT_KEYWORDS", "人工智能,科技,AI,大数据,机器学习"
        ).split(",") if kw.strip()
    ]
    """定时采集默认关键词列表（逗号分隔，支持环境变量覆盖）。"""


settings = Settings()
