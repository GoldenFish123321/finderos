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
from app.models.db import init_db, seed_default_data

# 配置结构化日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def make_app() -> tornado.web.Application:
    """
    创建 Tornado Web 应用实例。
    配置路由、安全策略和模式。
    """
    # cookie_secret: 优先使用环境变量，否则随机生成
    cookie_secret = settings.COOKIE_SECRET
    if not cookie_secret:
        cookie_secret = secrets.token_hex(32)
        settings.COOKIE_SECRET = cookie_secret  # 回写 settings，供加密模块使用
        logger.warning("COOKIE_SECRET 未设置，使用随机值（重启后所有会话失效）")

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
        ],
        template_path="app/templates",
        static_path="app/static",
        cookie_secret=cookie_secret,
        login_url=settings.LOGIN_URL,
        xsrf_cookies=settings.XSRF_COOKIES,
        debug=settings.DEBUG,
    )


if __name__ == "__main__":
    # 初始化数据库（自动建表）
    init_db()

    # 插入种子数据（默认角色、管理员、功能）
    seed_default_data()

    # 创建应用
    app = make_app()

    # 启动 HTTP 服务器
    bind_address = os.environ.get("BIND_ADDRESS", "127.0.0.1")
    app.listen(settings.PORT, bind_address)
    logger.info("=" * 50)
    logger.info("  瞭望与问数系统 (DataFinderAgentOS) v0.2")
    logger.info("  Server started: http://localhost:%d/", settings.PORT)
    logger.info("=" * 50)

    # 启动 Tornado 事件循环
    tornado.ioloop.IOLoop.current().start()
