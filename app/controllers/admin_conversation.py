"""
admin_conversation.py — 管理侧会话管理

管理员可查看所有用户前台会话、筛选用户、查看消息详情并删除任意会话。
"""
import tornado.web

from app.controllers.admin_base import AdminBaseHandler
from app.models.db import get_db
from app.models.conversation import ConversationRepository
from app.utils.security import write_audit_log


def _has_conversation_manage_permission(username: str) -> bool:
    """检查当前用户角色是否拥有会话管理功能节点。"""
    if not username:
        return False
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) as cnt
            FROM users u
            JOIN role_functions rf ON u.role_id = rf.role_id
            JOIN functions f ON rf.function_id = f.id
            WHERE u.username = ?
              AND f.route_path = ?
              AND f.is_enabled = 1
            """,
            (username, "/admin/conversation"),
        ).fetchone()
        return bool(row and row["cnt"] > 0)


class AdminConversationBaseHandler(AdminBaseHandler):
    """会话管理专用基类：额外执行功能级权限校验。"""

    REQUIRED_ROUTE = "/admin/conversation"

    def prepare(self):
        super().prepare()
        if self._finished:
            return
        if not _has_conversation_manage_permission(self.current_user):
            write_audit_log(
                action="ACCESS_DENIED_FUNCTION",
                username=self.current_user or "",
                target=self.request.path,
                detail=f"缺少功能权限: {self.REQUIRED_ROUTE}",
                client_ip=self.request.remote_ip or "",
            )
            self.set_status(403)
            self.write("""
            <div style="text-align:center;padding:60px 20px;">
                <i class="layui-icon layui-icon-close-fill" style="font-size:60px;color:#FF5722;"></i>
                <h2 style="margin-top:20px;">403 权限不足</h2>
                <p style="color:#999;margin-top:10px;">您没有会话管理权限，请联系系统管理员。</p>
                <a href="/admin" style="margin-top:20px;display:inline-block;">返回后台首页</a>
            </div>
            """)
            self.finish()


class AdminConversationListHandler(AdminConversationBaseHandler):
    """管理侧会话列表 + 详情。"""

    @tornado.web.authenticated
    def get(self):
        try:
            page = int(self.get_query_argument("page", 1))
        except (ValueError, TypeError):
            page = 1
        page = max(1, page)
        username_filter = self.get_query_argument("username", "").strip()
        keyword = self.get_query_argument("keyword", "").strip()
        selected_id = self.get_query_argument("id", "").strip()

        conversations, total = ConversationRepository.get_all_admin(
            page=page, page_size=20, username=username_filter, keyword=keyword,
        )
        total_pages = max(1, (total + 20 - 1) // 20)
        usernames = ConversationRepository.get_usernames()
        stats = ConversationRepository.get_admin_stats()

        selected_conv = None
        messages = []
        if selected_id:
            try:
                conv_id = int(selected_id)
            except (ValueError, TypeError):
                conv_id = 0
            if conv_id:
                selected_conv = ConversationRepository.get_by_id(conv_id)
                if selected_conv:
                    messages = ConversationRepository.get_messages(conv_id, limit=200)

        self.render(
            "admin/conversation_list.html",
            title="会话管理 — 瞭望与问数系统",
            username=self.current_user,
            conversations=conversations,
            users=usernames,
            stats=stats,
            page=page,
            total=total,
            total_pages=total_pages,
            username_filter=username_filter,
            keyword=keyword,
            selected_conv=selected_conv,
            messages=messages,
            xsrf_token=self.xsrf_token.decode() if isinstance(self.xsrf_token, bytes) else self.xsrf_token,
        )


class AdminConversationDeleteHandler(AdminConversationBaseHandler):
    """管理员删除任意会话。"""

    @tornado.web.authenticated
    def post(self):
        try:
            conv_id = int(self.get_body_argument("id", 0))
        except (ValueError, TypeError):
            self.redirect("/admin/conversation?msg=无效的会话ID")
            return

        conv = ConversationRepository.get_by_id(conv_id)
        if not conv:
            self.redirect("/admin/conversation?msg=会话不存在")
            return

        ConversationRepository.delete(conv_id)
        write_audit_log(
            action="ADMIN_CONVERSATION_DELETE",
            username=self.current_user,
            target=f"conversation:{conv_id}",
            detail=f"owner={conv.get('username', '')}, title={conv.get('title', '')}",
            client_ip=self.request.remote_ip or "",
        )
        self.redirect("/admin/conversation?msg=已删除会话")
