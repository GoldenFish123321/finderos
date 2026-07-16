"""
main.py — 瞭望与问数系统 (DataFinderAgentOS) 主入口

基于 Tornado 异步 Web 框架构建的轻量级数据查询与分析平台。
"""

import logging
import os
import signal

import tornado.ioloop
import tornado.web
from tornado.httpserver import HTTPServer

from app.config.settings import settings
from app.utils.security import _ensure_secret_key

# ── 模块级日志（必须在任何使用 logger 的函数之前定义）──
logger = logging.getLogger(__name__)
from app.controllers.auth import LoginHandler, LogoutHandler, RegisterHandler, FaceRegisterHandler, FaceLoginHandler
from app.controllers.home import IndexHandler
from app.controllers.admin_home import AdminIndexHandler, AdminDashboardHandler, AdminDashboardApiHandler
from app.controllers.admin_user import (
    UserListHandler, UserFormHandler, UserDeleteHandler, UserToggleHandler,
    UserBatchDeleteHandler, UserBatchToggleHandler, ChangePasswordHandler,
)
from app.controllers.admin_role import (
    RoleListHandler, RoleFormHandler, RoleDeleteHandler,
)
from app.controllers.admin_function import (
    FunctionListHandler, FunctionFormHandler, FunctionDeleteHandler, FunctionToggleHandler,
)
from app.controllers.admin_menu import MenuHandler, MenuSortHandler
from app.controllers.admin_watch import (
    WatchHandler, WatchStreamHandler, WatchSaveHandler, WatchDeepCollectHandler,
)
from app.controllers.admin_watch_source import (
    WatchSourceListHandler, WatchSourceFormHandler,
    WatchSourceDeleteHandler, WatchSourceToggleHandler,
)
from app.controllers.admin_warehouse import (
    WarehouseHandler, WarehouseDetailHandler, WarehouseDeleteHandler,
    WarehouseBatchDeleteHandler, WarehouseDeepCollectHandler, WatchLogHandler,
)
from app.controllers.admin_model import (
    ModelListHandler, ModelFormHandler, ModelQuickConfigHandler,
    ModelQuickConfigTestHandler, ModelDeleteHandler, ModelToggleHandler,
    ModelDefaultHandler, ModelApiListHandler,
)
from app.controllers.admin_interface import (
    InterfaceListHandler, InterfaceFormHandler, InterfaceDeleteHandler,
    InterfaceToggleHandler, InterfaceTestHandler, InterfaceApiListHandler,
)
from app.controllers.admin_employee import (
    EmployeeListHandler, EmployeeFormHandler, EmployeeDeleteHandler,
    EmployeeToggleHandler, EmployeeInvokeHandler, EmployeeApiListHandler,
    EmployeeTestPageHandler,
)
from app.controllers.admin_conversation import (
    AdminConversationListHandler, AdminConversationDeleteHandler,
)
from app.controllers.admin_message import (
    AdminMessageListHandler, AdminMessageDeleteHandler,
    AdminMessageMarkHandler, AdminMessageBatchHandler,
)
from app.controllers.admin_skill import (
    SkillListHandler, SkillFormHandler, SkillDeleteHandler, SkillToggleHandler,
)
from app.controllers.admin_config import SystemConfigHandler
from app.controllers.admin_sentiment import (
    AdminSentimentHandler, AdminSentimentApiHandler,
    AdminSentimentScanHandler, AdminSentimentAlertDetailHandler,
    AdminSentimentResolveHandler, AdminSentimentAnalyzeHandler,
)
from app.controllers.admin_mcp import (
    MCPToolListHandler, MCPToolFormHandler, MCPToolDeleteHandler,
    MCPToolToggleHandler, MCPToolTestHandler, MCPToolReloadHandler,
    MCPToolTestLogsHandler,
)
from app.controllers.user_chat import (
    UserChatPageHandler, UserModelListHandler, UserEmployeeListHandler,
    UserConversationListHandler, UserConversationCreateHandler,
    UserConversationDeleteHandler, UserConversationMessagesHandler,
    UserChatStreamHandler, UserEmployeeInvokeHandler,
    UserChatTTSHandler,
)
from app.models.db import init_db, seed_default_data
from app.services.scheduler import CollectionScheduler, SentimentScanner

# 配置结构化日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


def make_app() -> tornado.web.Application:
    """
    创建 Tornado Web 应用实例。
    配置路由、安全策略和模式。
    """
    # cookie_secret: 使用 settings 中已有的值（在 __main__ 块中已初始化）
    cookie_secret = settings.COOKIE_SECRET

    # 计算相对于 main.py 所在目录的绝对路径
    _base_dir = os.path.dirname(os.path.abspath(__file__))
    _template_dir = os.path.join(_base_dir, "app", "templates")
    _static_dir = os.path.join(_base_dir, "app", "static")

    return tornado.web.Application(
        [
            # 登录/登出/注册
            (r"/", LoginHandler),
            (r"/logout", LogoutHandler),
            (r"/register", RegisterHandler),
            (r"/api/face/register", FaceRegisterHandler),
            (r"/api/face/login", FaceLoginHandler),
            (r"/index", IndexHandler),

            # 管理后台 — Dashboard
            (r"/admin", AdminIndexHandler),

            # 管理后台 — 用户管理
            (r"/admin/user", UserListHandler),
            (r"/admin/user/add", UserFormHandler),
            (r"/admin/user/edit", UserFormHandler),
            (r"/admin/user/delete", UserDeleteHandler),
            (r"/admin/user/toggle", UserToggleHandler),
            (r"/admin/user/batch-delete", UserBatchDeleteHandler),
            (r"/admin/user/batch-toggle", UserBatchToggleHandler),
            (r"/admin/user/change-password", ChangePasswordHandler),

            # 管理后台 — 角色管理
            (r"/admin/role", RoleListHandler),
            (r"/admin/role/add", RoleFormHandler),
            (r"/admin/role/edit", RoleFormHandler),
            (r"/admin/role/delete", RoleDeleteHandler),

            # 管理后台 — 功能管理
            (r"/admin/function", FunctionListHandler),
            (r"/admin/function/add", FunctionFormHandler),
            (r"/admin/function/edit", FunctionFormHandler),
            (r"/admin/function/delete", FunctionDeleteHandler),
            (r"/admin/function/toggle", FunctionToggleHandler),

            # 管理后台 — 菜单管理
            (r"/admin/menu", MenuHandler),
            (r"/admin/menu/sort", MenuSortHandler),

            # ========== Day6-2 新增模块 ==========
            # 瞭望采集
            (r"/admin/watch", WatchHandler),
            (r"/admin/watch/stream", WatchStreamHandler),
            (r"/admin/watch/save", WatchSaveHandler),
            (r"/admin/watch/deep-collect", WatchDeepCollectHandler),

            # 瞭源管理
            (r"/admin/watch/log", WatchLogHandler),
            (r"/admin/watch/source", WatchSourceListHandler),
            (r"/admin/watch/source/add", WatchSourceFormHandler),
            (r"/admin/watch/source/edit", WatchSourceFormHandler),
            (r"/admin/watch/source/delete", WatchSourceDeleteHandler),
            (r"/admin/watch/source/toggle", WatchSourceToggleHandler),

            # 数据仓库
            (r"/admin/warehouse", WarehouseHandler),
            (r"/admin/warehouse/detail", WarehouseDetailHandler),
            (r"/admin/warehouse/delete", WarehouseDeleteHandler),
            (r"/admin/warehouse/batch-delete", WarehouseBatchDeleteHandler),
            # 深度采集
            (r"/admin/warehouse/deep-collect", WarehouseDeepCollectHandler),

            # 模型引擎
            (r"/admin/model", ModelListHandler),
            (r"/admin/model/config/test", ModelQuickConfigTestHandler),
            (r"/admin/model/config", ModelQuickConfigHandler),
            (r"/admin/model/add", ModelFormHandler),
            (r"/admin/model/edit", ModelFormHandler),
            (r"/admin/model/delete", ModelDeleteHandler),
            (r"/admin/model/toggle", ModelToggleHandler),
            (r"/admin/model/default", ModelDefaultHandler),
            (r"/admin/api/model/list", ModelApiListHandler),
            # 会话管理：管理员查看/筛选/删除所有用户会话
            (r"/admin/conversation", AdminConversationListHandler),
            (r"/admin/conversation/delete", AdminConversationDeleteHandler),
            # 消息管理：管理员逐条管理跨会话消息（Issue #18）
            (r"/admin/message", AdminMessageListHandler),
            (r"/admin/message/delete", AdminMessageDeleteHandler),
            (r"/admin/message/mark", AdminMessageMarkHandler),
            (r"/admin/message/batch", AdminMessageBatchHandler),
            # 接口管理：API 接口模板 CRUD / 测试 / 数字员工联动
            (r"/admin/interface", InterfaceListHandler),
            (r"/admin/interface/add", InterfaceFormHandler),
            (r"/admin/interface/edit", InterfaceFormHandler),
            (r"/admin/interface/delete", InterfaceDeleteHandler),
            (r"/admin/interface/toggle", InterfaceToggleHandler),
            (r"/admin/interface/test", InterfaceTestHandler),
            (r"/admin/api/interface/list", InterfaceApiListHandler),
            # ========== v0.4 新增模块 ==========
            # 数字化员工
            (r"/admin/employee", EmployeeListHandler),
            (r"/admin/employee/add", EmployeeFormHandler),
            (r"/admin/employee/edit", EmployeeFormHandler),
            (r"/admin/employee/delete", EmployeeDeleteHandler),
            (r"/admin/employee/toggle", EmployeeToggleHandler),
            # 员工调用（SSE 流式 / JSON 响应）
            (r"/admin/employee/invoke", EmployeeInvokeHandler),
            (r"/admin/api/employee/list", EmployeeApiListHandler),
            # 员工测试对话页
            (r"/admin/employee/test", EmployeeTestPageHandler),

            # 技能管理
            (r"/admin/skill", SkillListHandler),
            (r"/admin/skill/add", SkillFormHandler),
            (r"/admin/skill/edit", SkillFormHandler),
            (r"/admin/skill/delete", SkillDeleteHandler),
            (r"/admin/skill/toggle", SkillToggleHandler),

            # ========== v0.11 系统设置 ==========
            (r"/admin/config", SystemConfigHandler),

            # ========== v1.2.0 数智大屏 ==========
            (r"/admin/dashboard", AdminDashboardHandler),
            (r"/admin/api/dashboard", AdminDashboardApiHandler),

            # ========== v1.2.0 舆情大屏 ==========
            (r"/admin/sentiment", AdminSentimentHandler),
            (r"/admin/api/sentiment", AdminSentimentApiHandler),
            (r"/admin/api/sentiment/scan", AdminSentimentScanHandler),
            (r"/admin/api/sentiment/detail", AdminSentimentAlertDetailHandler),
            (r"/admin/api/sentiment/resolve", AdminSentimentResolveHandler),
            (r"/admin/api/sentiment/analyze", AdminSentimentAnalyzeHandler),

            # ========== v0.10 MCP 工具管理 ==========
            (r"/admin/mcp/tool", MCPToolListHandler),
            (r"/admin/mcp/tool/add", MCPToolFormHandler),
            (r"/admin/mcp/tool/edit", MCPToolFormHandler),
            (r"/admin/mcp/tool/delete", MCPToolDeleteHandler),
            (r"/admin/mcp/tool/toggle", MCPToolToggleHandler),
            (r"/admin/mcp/tool/test", MCPToolTestHandler),
            (r"/admin/mcp/tool/test-logs", MCPToolTestLogsHandler),
            (r"/admin/mcp/reload", MCPToolReloadHandler),

            # ========== v0.4 用户前台-智能问数 ==========
            # 前台对话主页
            (r"/chat", UserChatPageHandler),
            # 前台 SSE 流式 AI 对话
            (r"/chat/stream", UserChatStreamHandler),
            # 前台 @数字员工 SSE 流式调用
            (r"/chat/employee/invoke", UserEmployeeInvokeHandler),
            # 前台 API: 模型列表
            (r"/api/chat/models", UserModelListHandler),
            # 前台 API: 数字员工列表
            (r"/api/chat/employees", UserEmployeeListHandler),
            # 前台 API: 对话管理（列表/创建/删除/消息）
            (r"/api/chat/conversation/list", UserConversationListHandler),
            (r"/api/chat/conversation/create", UserConversationCreateHandler),
            (r"/api/chat/conversation/delete", UserConversationDeleteHandler),
            (r"/api/chat/conversation/messages", UserConversationMessagesHandler),
            # TTS 语音合成（Edge TTS）
            (r"/api/chat/tts", UserChatTTSHandler),
        ],
        template_path=_template_dir,
        static_path=_static_dir,
        cookie_secret=cookie_secret,
        login_url=settings.LOGIN_URL,
        xsrf_cookies=settings.XSRF_COOKIES,
        debug=settings.DEBUG,
    )


if __name__ == "__main__":
    # 确保 COOKIE_SECRET 在数据库初始化之前已设置（加密模块依赖此密钥）
    # _ensure_secret_key() 统一管理密钥：环境变量 → .secret_key 文件 → 自动生成
    _ensure_secret_key()

    # 初始化数据库（自动建表）
    init_db()

    # 插入种子数据（默认角色、管理员、功能）
    seed_default_data()

    # v0.11: 从数据库加载可配置的系统设置，覆盖默认值
    settings.load_from_db()

    # v0.10: 显式注册 MCP 工具（确保数据库驱动工具在启动时加载）
    from app.mcp.tools import register_all_tools
    register_all_tools()

    # 创建应用
    app = make_app()

    # 启动定时采集调度器 (v0.6)
    scheduler = CollectionScheduler(
        app, check_interval_ms=settings.COLLECTOR_INTERVAL_MINUTES * 60 * 1000
    )
    scheduler.start()

    # 启动定时舆情扫描器 (v1.2.0) — 每5分钟
    _sentiment_scanner = SentimentScanner(check_interval_ms=300000)
    _sentiment_scanner.start()

    # 注册优雅关闭信号处理器
    ioloop = tornado.ioloop.IOLoop.current()
    def _shutdown(signum, frame):
        logger.info(f"收到信号 {signum}，正在优雅关闭...")
        scheduler.stop()
        _sentiment_scanner.stop()
        ioloop.add_callback(ioloop.stop)
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    # 启动 HTTP 服务器
    bind_address = os.environ.get("BIND_ADDRESS", "127.0.0.1")
    app.listen(settings.PORT, bind_address)
    logger.info("=" * 50)
    logger.info("  瞭望与问数系统 (DataFinderAgentOS) v%s", settings.VERSION)
    logger.info("  Server started: http://localhost:%d/", settings.PORT)
    logger.info("=" * 50)

    # 启动 Tornado 事件循环
    tornado.ioloop.IOLoop.current().start()
