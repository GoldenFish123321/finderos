"""
admin_message.py — 管理侧独立消息管理 (Issue #18)

管理员可逐条查看、筛选、标记、删除所有跨会话消息。
与舆情大屏联动：支持按敏感内容筛选和内容审查标记。
"""
import logging
from urllib.parse import urlparse

import tornado.web

from app.controllers.admin_base import AdminBaseHandler
from app.models.db import get_db
from app.models.conversation import ConversationRepository
from app.utils.security import write_audit_log

logger = logging.getLogger(__name__)


def _has_message_manage_permission(username: str) -> bool:
    """检查当前用户角色是否拥有消息管理功能节点。"""
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
            (username, "/admin/message"),
        ).fetchone()
        return bool(row and row["cnt"] > 0)


class AdminMessageBaseHandler(AdminBaseHandler):
    """消息管理专用基类：额外执行功能级权限校验。"""

    REQUIRED_ROUTE = "/admin/message"

    def prepare(self):
        super().prepare()
        if self._finished:
            return
        if not _has_message_manage_permission(self.current_user):
            write_audit_log(
                action="ACCESS_DENIED_FUNCTION",
                username=self.current_user or "",
                target=self.request.path,
                detail=f"缺少功能权限: {self.REQUIRED_ROUTE}",
                client_ip=self.request.remote_ip or "",
            )
            self.set_status(403)
            self.render("admin/403.html", message="您没有消息管理权限，请联系系统管理员。", link="/admin", link_text="返回后台首页")


class AdminMessageListHandler(AdminMessageBaseHandler):
    """管理侧消息列表（跨会话逐条管理）。"""

    @tornado.web.authenticated
    def get(self):
        try:
            page = int(self.get_query_argument("page", 1))
        except (ValueError, TypeError):
            page = 1
        page = max(1, page)

        username_filter = self.get_query_argument("username", "").strip()
        keyword = self.get_query_argument("keyword", "").strip()
        role_filter = self.get_query_argument("role", "").strip()
        sensitive_filter = self.get_query_argument("is_sensitive", "").strip()
        review_filter = self.get_query_argument("review_status", "").strip()
        date_from = self.get_query_argument("date_from", "").strip()
        date_to = self.get_query_argument("date_to", "").strip()

        try:
            messages, total = ConversationRepository.get_all_messages_admin(
                page=page,
                page_size=30,
                username=username_filter,
                keyword=keyword,
                role=role_filter,
                is_sensitive=sensitive_filter,
                review_status=review_filter,
                date_from=date_from,
                date_to=date_to,
            )
            total_pages = max(1, (total + 30 - 1) // 30)
            usernames = ConversationRepository.get_message_usernames()
            stats = ConversationRepository.get_message_stats()
        except Exception as e:
            logger.error(f"消息列表查询失败: {e}")
            messages, total = [], 0
            total_pages = 1
            usernames, stats = [], {"total": 0, "sensitive": 0, "pending": 0, "flagged": 0}

        self.render(
            "admin/message_list.html",
            title="消息管理 — 瞭望与问数系统",
            username=self.current_user,
            messages=messages,
            users=usernames,
            stats=stats,
            page=page,
            total=total,
            total_pages=total_pages,
            username_filter=username_filter,
            keyword=keyword,
            role_filter=role_filter,
            sensitive_filter=sensitive_filter,
            review_filter=review_filter,
            date_from=date_from,
            date_to=date_to,
            xsrf_token=self.xsrf_token.decode() if isinstance(self.xsrf_token, bytes) else self.xsrf_token,
        )


class AdminMessageDeleteHandler(AdminMessageBaseHandler):
    """管理员删除单条消息。"""

    @tornado.web.authenticated
    def post(self):
        try:
            msg_id = int(self.get_body_argument("id", 0))
        except (ValueError, TypeError):
            self.redirect("/admin/message?msg=无效的消息ID")
            return

        if not ConversationRepository.delete_message(msg_id):
            self.redirect("/admin/message?msg=消息不存在")
            return

        write_audit_log(
            action="ADMIN_MESSAGE_DELETE",
            username=self.current_user,
            target=f"message:{msg_id}",
            detail="管理员删除消息",
            client_ip=self.request.remote_ip or "",
        )
        # 安全回跳：仅允许同源 Referer 或直接回退到消息列表
        referer = self.request.headers.get("Referer", "")
        safe_redirect = "/admin/message?msg=已删除消息"
        if referer:
            try:
                parsed = urlparse(referer)
                if (not parsed.netloc or parsed.netloc == self.request.host) and "/admin/message" in parsed.path:
                    safe_redirect = referer
            except Exception:
                pass
        self.redirect(safe_redirect)


class AdminMessageMarkHandler(AdminMessageBaseHandler):
    """标记消息（敏感标记 / 审核状态变更）。"""

    @tornado.web.authenticated
    def post(self):
        try:
            msg_id = int(self.get_body_argument("id", 0))
        except (ValueError, TypeError):
            self.write({"code": 1, "msg": "无效的消息ID"})
            return

        action = self.get_body_argument("action", "").strip()

        if action == "toggle_sensitive":
            is_sensitive = self.get_body_argument("value", "0")
            ConversationRepository.mark_message_sensitive(msg_id, 1 if is_sensitive == "1" else 0)
            write_audit_log(
                action="ADMIN_MESSAGE_MARK_SENSITIVE",
                username=self.current_user,
                target=f"message:{msg_id}",
                detail=f"敏感标记={'是' if is_sensitive == '1' else '否'}",
                client_ip=self.request.remote_ip or "",
            )
            self.write({"code": 0, "msg": "标记成功"})

        elif action == "set_review":
            review_status = self.get_body_argument("value", "reviewed").strip()
            ConversationRepository.mark_message_reviewed(msg_id, review_status)
            write_audit_log(
                action="ADMIN_MESSAGE_REVIEW",
                username=self.current_user,
                target=f"message:{msg_id}",
                detail=f"审核状态={review_status}",
                client_ip=self.request.remote_ip or "",
            )
            self.write({"code": 0, "msg": "审核状态已更新"})

        else:
            self.write({"code": 1, "msg": "未知操作"})


class AdminMessageBatchHandler(AdminMessageBaseHandler):
    """批量操作消息。"""

    @tornado.web.authenticated
    def post(self):
        ids_str = self.get_body_argument("ids", "").strip()
        action = self.get_body_argument("action", "").strip()

        if not ids_str:
            self.write({"code": 1, "msg": "请选择消息"})
            return

        try:
            msg_ids = [int(x.strip()) for x in ids_str.split(",") if x.strip()]
        except (ValueError, TypeError):
            self.write({"code": 1, "msg": "无效的消息ID列表"})
            return

        if not msg_ids:
            self.write({"code": 1, "msg": "无效的消息ID列表"})
            return

        count = 0
        if action == "batch_delete":
            with get_db() as conn:
                for mid in msg_ids:
                    cur = conn.execute("DELETE FROM conversation_messages WHERE id = ?", (mid,))
                    if cur.rowcount > 0:
                        count += 1
                conn.commit()
            write_audit_log(
                action="ADMIN_MESSAGE_BATCH_DELETE",
                username=self.current_user,
                target=f"messages:{len(msg_ids)}",
                detail=f"批量删除 {count} 条消息",
                client_ip=self.request.remote_ip or "",
            )
        elif action == "batch_mark_sensitive":
            with get_db() as conn:
                for mid in msg_ids:
                    cur = conn.execute(
                        "UPDATE conversation_messages SET is_sensitive = 1 WHERE id = ?", (mid,)
                    )
                    if cur.rowcount > 0:
                        count += 1
                conn.commit()
            write_audit_log(
                action="ADMIN_MESSAGE_BATCH_SENSITIVE",
                username=self.current_user,
                target=f"messages:{len(msg_ids)}",
                detail=f"批量标记 {count} 条消息为敏感",
                client_ip=self.request.remote_ip or "",
            )
        elif action == "batch_mark_reviewed":
            with get_db() as conn:
                for mid in msg_ids:
                    cur = conn.execute(
                        "UPDATE conversation_messages SET review_status = 'reviewed' WHERE id = ?", (mid,)
                    )
                    if cur.rowcount > 0:
                        count += 1
                conn.commit()
            write_audit_log(
                action="ADMIN_MESSAGE_BATCH_REVIEWED",
                username=self.current_user,
                target=f"messages:{len(msg_ids)}",
                detail=f"批量审核通过 {count} 条消息",
                client_ip=self.request.remote_ip or "",
            )
        else:
            self.write({"code": 1, "msg": "未知操作"})
            return

        self.write({"code": 0, "msg": f"成功处理 {count} 条消息"})
