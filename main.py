"""
main.py — 瞭望与问数系统 (DataFinderAgentOS) 主入口

基于 Tornado 异步 Web 框架构建的轻量级数据查询与分析平台。
"""

import logging
import os
import secrets

import tornado.ioloop
import tornado.web
from tornado.httpserver import HTTPServer

from app.config.settings import settings

# ── 模块级日志（必须在任何使用 logger 的函数之前定义）──
logger = logging.getLogger(__name__)

# ── COOKIE_SECRET 持久化文件路径 ──
_SECRET_KEY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".secret_key")


def _load_or_create_secret_key() -> str:
    """加载或创建持久化的 COOKIE_SECRET。

    优先级：
    1. 环境变量 COOKIE_SECRET（生产环境推荐）
    2. .secret_key 文件（自动生成，跨重启持久化）
    3. 自动生成并保存到 .secret_key 文件

    这确保 API Key 加密密钥在重启后保持一致，避免数据丢失。
    """
    # 1. 环境变量优先
    env_secret = os.environ.get("COOKIE_SECRET", "")
    if env_secret:
        return env_secret

    # 2. 尝试从文件加载
    try:
        if os.path.exists(_SECRET_KEY_FILE):
            with open(_SECRET_KEY_FILE, "r") as f:
                saved = f.read().strip()
                if saved:
                    logger.info("已从 .secret_key 文件加载持久化密钥")
                    return saved
    except OSError as e:
        logger.warning(f"读取 .secret_key 文件失败: {e}")

    # 3. 生成新密钥并持久化
    new_secret = secrets.token_hex(32)
    try:
        with open(_SECRET_KEY_FILE, "w") as f:
            f.write(new_secret)
        logger.info("已生成新的持久化密钥并保存到 .secret_key 文件")
    except OSError as e:
        logger.warning(f"无法保存 .secret_key 文件: {e}，密钥仅存在于本次会话")

    return new_secret
from app.controllers.auth import LoginHandler, LogoutHandler, RegisterHandler
from app.controllers.home import IndexHandler
from app.controllers.admin_home import AdminIndexHandler
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
from app.controllers.admin_watch import WatchHandler, WatchSaveHandler, WatchDeepCollectHandler
from app.controllers.admin_watch_source import (
    WatchSourceListHandler, WatchSourceFormHandler,
    WatchSourceDeleteHandler, WatchSourceToggleHandler,
)
from app.controllers.admin_warehouse import (
    WarehouseHandler, WarehouseDetailHandler, WarehouseDeleteHandler,
    WarehouseBatchDeleteHandler, WarehouseDeepCollectHandler,
)
from app.controllers.admin_model import (
    ModelListHandler, ModelFormHandler, ModelDeleteHandler,
    ModelToggleHandler, ModelDefaultHandler, ModelApiListHandler,
    ModelChatHandler, ModelChatPageHandler,
    ConversationListHandler, ConversationCreateHandler,
    ConversationDeleteHandler, ConversationMessagesHandler,
)
from app.controllers.admin_employee import (
    EmployeeListHandler, EmployeeFormHandler, EmployeeDeleteHandler,
    EmployeeToggleHandler, EmployeeInvokeHandler, EmployeeApiListHandler,
    EmployeeTestPageHandler,
)
from app.controllers.user_chat import (
    UserChatPageHandler, UserModelListHandler, UserEmployeeListHandler,
    UserConversationListHandler, UserConversationCreateHandler,
    UserConversationDeleteHandler, UserConversationMessagesHandler,
    UserChatStreamHandler, UserEmployeeInvokeHandler,
)
from app.models.db import init_db, seed_default_data
from app.services.scheduler import CollectionScheduler

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

    return tornado.web.Application(
        [
            # 登录/登出/注册
            (r"/", LoginHandler),
            (r"/logout", LogoutHandler),
            (r"/register", RegisterHandler),
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
            (r"/admin/watch/save", WatchSaveHandler),
            (r"/admin/watch/deep-collect", WatchDeepCollectHandler),

            # 瞭源管理
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
            (r"/admin/model/add", ModelFormHandler),
            (r"/admin/model/edit", ModelFormHandler),
            (r"/admin/model/delete", ModelDeleteHandler),
            (r"/admin/model/toggle", ModelToggleHandler),
            (r"/admin/model/default", ModelDefaultHandler),
            (r"/admin/api/model/list", ModelApiListHandler),
            # 模型对话测试
            (r"/admin/model/chat", ModelChatPageHandler),
            (r"/admin/model/chat/stream", ModelChatHandler),

            # 多轮对话管理 (v0.5.0)
            (r"/admin/api/conversation/list", ConversationListHandler),
            (r"/admin/api/conversation/create", ConversationCreateHandler),
            (r"/admin/api/conversation/delete", ConversationDeleteHandler),
            (r"/admin/api/conversation/messages", ConversationMessagesHandler),

            # ========== v0.3.0 新增模块 ==========
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

            # ========== v0.3.0 用户前台-智能问数 ==========
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
        ],
        template_path="app/templates",
        static_path="app/static",
        cookie_secret=cookie_secret,
        login_url=settings.LOGIN_URL,
        xsrf_cookies=settings.XSRF_COOKIES,
        debug=settings.DEBUG,
    )


if __name__ == "__main__":
    # 确保 COOKIE_SECRET 在数据库初始化之前已设置（加密模块依赖此密钥）
    # 使用持久化密钥加载策略，避免重启后 API Key 无法解密
    if not settings.COOKIE_SECRET:
        settings.COOKIE_SECRET = _load_or_create_secret_key()

    # 初始化数据库（自动建表）
    init_db()

    # 插入种子数据（默认角色、管理员、功能）
    seed_default_data()

    # 创建应用
    app = make_app()

    # 启动定时采集调度器 (v0.6.0)
    scheduler = CollectionScheduler(app, check_interval_ms=60000)
    scheduler.start()

    # 启动 HTTP 服务器
    bind_address = os.environ.get("BIND_ADDRESS", "127.0.0.1")
    app.listen(settings.PORT, bind_address)
    logger.info("=" * 50)
    logger.info("  瞭望与问数系统 (DataFinderAgentOS) v0.2")
    logger.info("  Server started: http://localhost:%d/", settings.PORT)
    logger.info("=" * 50)

    # 启动 Tornado 事件循环
    tornado.ioloop.IOLoop.current().start()
