"""
main.py — 瞭望与问数系统 (DataFinderAgentOS) 主入口

基于 Tornado 异步 Web 框架构建的轻量级数据查询与分析平台。
"""

import logging
import os

import tornado.ioloop
import tornado.web
from tornado.httpserver import HTTPServer

from app.config.settings import settings
from app.utils.security import _ensure_secret_key

# ── 模块级日志（必须在任何使用 logger 的函数之前定义）──
logger = logging.getLogger(__name__)
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
    ModelListHandler, ModelFormHandler, ModelDeleteHandler,
    ModelToggleHandler, ModelDefaultHandler, ModelApiListHandler,
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
from app.controllers.admin_skill import (
    SkillListHandler, SkillFormHandler, SkillDeleteHandler, SkillToggleHandler,
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
            (r"/admin/model/add", ModelFormHandler),
            (r"/admin/model/edit", ModelFormHandler),
            (r"/admin/model/delete", ModelDeleteHandler),
            (r"/admin/model/toggle", ModelToggleHandler),
            (r"/admin/model/default", ModelDefaultHandler),
            (r"/admin/api/model/list", ModelApiListHandler),
            # 会话管理：管理员查看/筛选/删除所有用户会话
            (r"/admin/conversation", AdminConversationListHandler),
            (r"/admin/conversation/delete", AdminConversationDeleteHandler),
            # 接口管理：API 接口模板 CRUD / 测试 / 数字员工联动
            (r"/admin/interface", InterfaceListHandler),
            (r"/admin/interface/add", InterfaceFormHandler),
            (r"/admin/interface/edit", InterfaceFormHandler),
            (r"/admin/interface/delete", InterfaceDeleteHandler),
            (r"/admin/interface/toggle", InterfaceToggleHandler),
            (r"/admin/interface/test", InterfaceTestHandler),
            (r"/admin/api/interface/list", InterfaceApiListHandler),
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

            # 技能管理
            (r"/admin/skill", SkillListHandler),
            (r"/admin/skill/add", SkillFormHandler),
            (r"/admin/skill/edit", SkillFormHandler),
            (r"/admin/skill/delete", SkillDeleteHandler),
            (r"/admin/skill/toggle", SkillToggleHandler),

            # ========== v0.4.2 MCP 工具管理 ==========
            (r"/admin/mcp/tool", MCPToolListHandler),
            (r"/admin/mcp/tool/add", MCPToolFormHandler),
            (r"/admin/mcp/tool/edit", MCPToolFormHandler),
            (r"/admin/mcp/tool/delete", MCPToolDeleteHandler),
            (r"/admin/mcp/tool/toggle", MCPToolToggleHandler),
            (r"/admin/mcp/tool/test", MCPToolTestHandler),
            (r"/admin/mcp/tool/test-logs", MCPToolTestLogsHandler),
            (r"/admin/mcp/reload", MCPToolReloadHandler),

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
            # TTS 语音合成（Edge TTS）
            (r"/api/chat/tts", UserChatTTSHandler),
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
    # _ensure_secret_key() 统一管理密钥：环境变量 → .secret_key 文件 → 自动生成
    _ensure_secret_key()

    # 初始化数据库（自动建表）
    init_db()

    # 插入种子数据（默认角色、管理员、功能）
    seed_default_data()

    # 创建应用
    app = make_app()

    # 启动定时采集调度器 (v0.4.0)
    scheduler = CollectionScheduler(app, check_interval_ms=60000)
    scheduler.start()

    # 启动 HTTP 服务器
    bind_address = os.environ.get("BIND_ADDRESS", "127.0.0.1")
    app.listen(settings.PORT, bind_address)
    logger.info("=" * 50)
    logger.info("  瞭望与问数系统 (DataFinderAgentOS) v%s", settings.VERSION)
    logger.info("  Server started: http://localhost:%d/", settings.PORT)
    logger.info("=" * 50)

    # 启动 Tornado 事件循环
    tornado.ioloop.IOLoop.current().start()
