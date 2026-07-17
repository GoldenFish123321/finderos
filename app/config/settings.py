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
    VERSION = "1.10.1-beta"
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

    DEFAULT_WEATHER_CITY = os.environ.get("DEFAULT_WEATHER_CITY", "成都")
    """定位失败或用户拒绝定位时，手势天气查询使用的默认城市。"""

    # === 备份配置（#99） ===
    DB_BACKUP_PATH = "backups/"
    """数据库备份文件存放路径（相对于项目根目录）。"""

    DB_BACKUP_INTERVAL_DAYS = 7
    """数据库自动备份间隔天数。"""

    DB_BACKUP_KEEP_COUNT = 5
    """备份文件最大保留份数，超出自动清理旧文件。"""

    # === 日志配置（#99） ===
    LOG_LEVEL = "INFO"
    """应用日志级别：DEBUG / INFO / WARNING / ERROR。"""

    # === 通知配置（#99） ===
    SMTP_HOST = ""
    """SMTP 邮件服务器地址（为空则不启用邮件通知）。"""

    WEBHOOK_URL = ""
    """Webhook 通知 URL（为空则不启用 Webhook 通知）。"""

    # === 采集配置（#99） ===
    COLLECTOR_INTERVAL_MINUTES = 60
    """全局默认采集调度间隔（分钟）。"""

    # === 安全策略开关（#99） ===
    CAPTCHA_ENABLED = False
    """是否启用登录验证码。"""

    REGISTRATION_ENABLED = True
    """是否允许新用户注册。"""

    SESSION_EXPIRE_HOURS = 24
    """用户会话过期时间（小时）。"""

    # === 上传限制（#99） ===
    UPLOAD_MAX_SIZE_MB = 10
    """文件上传大小限制（MB）。"""

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
        "Permissions-Policy": "camera=(self), microphone=(), geolocation=(self)",
        # 严格化 CSP（借鉴陈子墨）：移除 unsafe-eval，收窄 connect-src，增加 frame-ancestors/base-uri/form-action
        # Issue #15: 添加 blob: 以允许 MediaPipe Hands WASM Worker
        # Dashboard: 允许 jsdelivr 加载 Three.js/ECharts 脚本，img-src https: 覆盖地球纹理；无需浏览器插件
        "Content-Security-Policy": (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data: https: blob:; "
            "media-src 'self' blob: https:; "
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
                "default_port": "PORT",
                "ai_default_model": "AI_DEFAULT_MODEL",
                "ai_default_temperature": "AI_DEFAULT_TEMPERATURE",
                "ai_default_max_tokens": "AI_DEFAULT_MAX_TOKENS",
                # #99 新增配置项映射
                "db_backup_path": "DB_BACKUP_PATH",
                "db_backup_interval_days": "DB_BACKUP_INTERVAL_DAYS",
                "db_backup_keep_count": "DB_BACKUP_KEEP_COUNT",
                "log_level": "LOG_LEVEL",
                "smtp_host": "SMTP_HOST",
                "webhook_url": "WEBHOOK_URL",
                "collector_interval_minutes": "COLLECTOR_INTERVAL_MINUTES",
                "captcha_enabled": "CAPTCHA_ENABLED",
                "registration_enabled": "REGISTRATION_ENABLED",
                "session_expire_hours": "SESSION_EXPIRE_HOURS",
                "upload_max_size_mb": "UPLOAD_MAX_SIZE_MB",
            }

            # 需要 int 类型转换的属性
            _INT_ATTRS = {
                "AI_DEFAULT_MAX_TOKENS", "PORT",
                "DB_BACKUP_INTERVAL_DAYS", "DB_BACKUP_KEEP_COUNT",
                "COLLECTOR_INTERVAL_MINUTES", "SESSION_EXPIRE_HOURS",
                "UPLOAD_MAX_SIZE_MB",
            }
            # 需要 float 类型转换的属性
            _FLOAT_ATTRS = {"AI_DEFAULT_TEMPERATURE"}
            # 需要 bool 类型转换的属性
            _BOOL_ATTRS = {"CAPTCHA_ENABLED", "REGISTRATION_ENABLED"}
            _RANGES = {
                "PORT": (1, 65535),
                "AI_DEFAULT_MAX_TOKENS": (1, 131072),
                "DB_BACKUP_INTERVAL_DAYS": (1, 365),
                "DB_BACKUP_KEEP_COUNT": (1, 365),
                "COLLECTOR_INTERVAL_MINUTES": (1, 1440),
                "SESSION_EXPIRE_HOURS": (1, 8760),
                "UPLOAD_MAX_SIZE_MB": (1, 1024),
            }

            for db_key, attr_name in _DB_KEY_MAP.items():
                if db_key in db_config and db_config[db_key]:
                    if attr_name == "PORT" and "PORT" in os.environ:
                        continue
                    raw_value = db_config[db_key]
                    try:
                        if attr_name in _FLOAT_ATTRS:
                            value = float(raw_value)
                            if not 0 <= value <= 2:
                                raise ValueError("value out of range")
                            setattr(self, attr_name, value)
                        elif attr_name in _INT_ATTRS:
                            value = int(raw_value)
                            low, high = _RANGES[attr_name]
                            if not low <= value <= high:
                                raise ValueError("value out of range")
                            setattr(self, attr_name, value)
                        elif attr_name in _BOOL_ATTRS:
                            normalized = str(raw_value).lower()
                            if normalized not in {"true", "false", "1", "0", "yes", "no"}:
                                raise ValueError("invalid boolean")
                            setattr(self, attr_name, normalized in ("true", "1", "yes"))
                        elif attr_name == "LOG_LEVEL":
                            value = str(raw_value).upper()
                            if value not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
                                raise ValueError("invalid log level")
                            setattr(self, attr_name, value)
                        else:
                            setattr(self, attr_name, raw_value)
                    except (ValueError, TypeError):
                        logger.warning(f"system_config.{db_key} 值 '{raw_value}' 无效，使用默认值")

            logger.info(f"已从 system_config 表加载 {len(db_config)} 项配置")
            logging.getLogger().setLevel(getattr(logging, self.LOG_LEVEL, logging.INFO))
        except Exception as e:
            logger.warning(f"从 system_config 表加载配置失败（将使用默认值）: {e}")


settings = Settings()
