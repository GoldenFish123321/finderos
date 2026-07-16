"""
settings.py — 应用配置管理中心

所有配置支持环境变量覆盖，适用于开发/测试/生产环境切换。
"""

import logging
import os

logger = logging.getLogger(__name__)


class Settings:
    """全局应用配置"""

    # === 应用版本（唯一硬编码位置） ===
    VERSION = "1.3.3-beta"
    """应用版本号。项目中所有版本展示均由此处统一管理。"""

    # === UI 可配置项（默认值，启动后被 DB system_config 表覆盖） ===
    SYSTEM_NAME = "瞭望与问数系统"
    """系统名称，显示在页面标题和头部导航栏。可通过管理后台 → 常规设置修改。"""

    SYSTEM_SUBTITLE = "DataFinderAgentOS"
    """系统副标题/英文名称，显示在头部版本号旁。"""

    SYSTEM_LOGO = ""
    """系统 Logo 图片路径（相对 static 目录），为空则显示文字 Logo。"""

    ICP_NUMBER = ""
    """ICP 备案号，显示在页面底部。"""

    AI_DEFAULT_MODEL = ""
    """AI 默认模型 ID（空 = 使用 is_default=1 的模型）。"""

    AI_DEFAULT_TEMPERATURE = 0.7
    """AI 默认温度参数（0-2），控制回复随机性。"""

    AI_DEFAULT_MAX_TOKENS = 4096
    """AI 默认最大输出 Token 数。"""

    # === 安全配置 ===
    COOKIE_SECRET = os.environ.get("COOKIE_SECRET", "")
    """Tornado 安全 Cookie 签名密钥。生产环境必须通过环境变量注入。"""

    ADMIN_DEFAULT_PASSWORD = os.environ.get("ADMIN_DEFAULT_PASSWORD", "")
    """首次初始化管理员密码；未设置时生成一次性随机密码。"""

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
        # Issue #15: 允许摄像头以供手势识别
        "Permissions-Policy": "camera=(self), microphone=(), geolocation=()",
        # 严格化 CSP（借鉴陈子墨）：移除 unsafe-eval，收窄 connect-src，增加 frame-ancestors/base-uri/form-action
        # Issue #15: 添加 blob: 以允许 MediaPipe Hands WASM Worker
        "Content-Security-Policy": (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data: https: blob:; "
            "media-src 'self' https:; "
            "font-src 'self' https://cdn.jsdelivr.net; "
            "connect-src 'self' https://cdn.jsdelivr.net blob: https://*.jsdelivr.net; "
            "worker-src 'self' blob:; "
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

    # === 数据库配置加载 ===

    def load_from_db(self) -> None:
        """从 system_config 表加载 UI 可配置项，覆盖默认值。

        调用时机：init_db() + seed_default_data() 完成之后（main.py 中调用）。
        容错：DB 读取失败时静默回退到类属性默认值。
        优先级：环境变量 > DB 值 > 类属性默认值（已在 __init__ 后生效）。
        """
        try:
            from app.models.system_config import SystemConfigRepository
            db_config = SystemConfigRepository.get_all_as_dict()
            if not db_config:
                logger.info("system_config 表为空，使用默认配置")
                return

            # 白名单：仅允许以下 key 覆盖 Settings 属性
            _DB_KEY_MAP = {
                "system_name": "SYSTEM_NAME",
                "system_subtitle": "SYSTEM_SUBTITLE",
                "system_logo": "SYSTEM_LOGO",
                "icp_number": "ICP_NUMBER",
                "ai_default_model": "AI_DEFAULT_MODEL",
                "ai_default_temperature": "AI_DEFAULT_TEMPERATURE",
                "ai_default_max_tokens": "AI_DEFAULT_MAX_TOKENS",
            }

            for db_key, attr_name in _DB_KEY_MAP.items():
                if db_key in db_config and db_config[db_key]:
                    raw_value = db_config[db_key]
                    # 类型转换：数值型属性
                    if attr_name in ("AI_DEFAULT_TEMPERATURE",):
                        try:
                            setattr(self, attr_name, float(raw_value))
                        except (ValueError, TypeError):
                            logger.warning(f"system_config.{db_key} 值 '{raw_value}' 无效，使用默认值")
                    elif attr_name in ("AI_DEFAULT_MAX_TOKENS",):
                        try:
                            setattr(self, attr_name, int(raw_value))
                        except (ValueError, TypeError):
                            logger.warning(f"system_config.{db_key} 值 '{raw_value}' 无效，使用默认值")
                    elif attr_name in ("AI_DEFAULT_MODEL",):
                        # 模型 ID 保留为字符串（模板中统一用字符串比较）
                        setattr(self, attr_name, raw_value)
                    else:
                        setattr(self, attr_name, raw_value)

            logger.info(f"已从 system_config 表加载 {len(db_config)} 项配置")
        except Exception as e:
            logger.warning(f"从 system_config 表加载配置失败（将使用默认值）: {e}")


settings = Settings()
