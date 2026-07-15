"""
admin_skill.py — 技能管理控制器

管理员管理技能库（新增/编辑/删除/启用禁用/分页）。
"""
import tornado.web
from app.controllers.admin_base import AdminBaseHandler
from app.models.skill import SkillRepository, SKILL_TYPES
from app.utils.security import write_audit_log

# MCP 工具列表（供 function 型技能关联）
MCP_TOOL_NAMES = [
    "search_warehouse",
    "get_recent_warehouse_data",
    "get_warehouse_stats",
    "collect_web_data",
    "deep_collect_url",
    "list_digital_employees",
    "get_random_music",
    "list_conversations",
    "get_conversation_messages",
    "load_skill",
]


class SkillListHandler(AdminBaseHandler):
    """技能列表页"""

    @tornado.web.authenticated
    def get(self):
        try:
            page = max(1, int(self.get_query_argument("page", 1)))
        except (ValueError, TypeError):
            page = 1
        skill_type = self.get_query_argument("type", "").strip()
        rows, total = SkillRepository.get_all(
            page=page, page_size=20, skill_type=skill_type
        )
        total_pages = max(1, (total + 20 - 1) // 20)
        stats = SkillRepository.get_stats()

        self.render(
            "admin/skill_list.html",
            title="技能管理 — 瞭望与问数系统",
            username=self.current_user,
            skills=rows,
            page=page,
            total=total,
            total_pages=total_pages,
            skill_type=skill_type,
            skill_types=SKILL_TYPES,
            stats=stats,
        )


class SkillFormHandler(AdminBaseHandler):
    """技能新增/编辑表单页"""

    @tornado.web.authenticated
    def get(self):
        skill_id = self.get_query_argument("id", None)
        skill = None
        if skill_id:
            try:
                skill = SkillRepository.get_by_id(int(skill_id))
            except (ValueError, TypeError):
                self.write('<script>alert("无效的技能ID");window.history.back();</script>')
                return
            if not skill:
                self.write('<script>alert("技能不存在");window.history.back();</script>')
                return

        self.render(
            "admin/skill_form.html",
            title="编辑技能" if skill else "新增技能",
            username=self.current_user,
            skill=skill,
            skill_types=SKILL_TYPES,
            mcp_tools=MCP_TOOL_NAMES,
        )

    @tornado.web.authenticated
    def post(self):
        skill_id = self.get_body_argument("id", None)
        name = self.get_body_argument("name", "").strip()
        description = self.get_body_argument("description", "").strip()
        skill_type = self.get_body_argument("skill_type", "prompt").strip()
        prompt_template = self.get_body_argument("prompt_template", "").strip()
        function_name = self.get_body_argument("function_name", "").strip()
        function_params = self.get_body_argument("function_params", "{}").strip()

        if not name:
            self.write('<script>alert("技能名称不能为空");window.history.back();</script>')
            return

        if skill_type not in ("prompt", "function"):
            self.write('<script>alert("无效的技能类型");window.history.back();</script>')
            return

        if skill_id:
            skill_id = int(skill_id)
            ok = SkillRepository.update(
                skill_id, name, description, skill_type,
                prompt_template, function_name, function_params,
            )
            msg = "更新成功" if ok else "更新失败（名称重复？）"
            write_audit_log(
                action="SKILL_UPDATE",
                username=self.current_user,
                target=f"skill:{skill_id}",
                detail=f"name={name}, type={skill_type}",
                client_ip=self.request.remote_ip or "",
            )
        else:
            new_id = SkillRepository.create(
                name, description, skill_type,
                prompt_template, function_name, function_params,
            )
            msg = "创建成功" if new_id > 0 else "创建失败（名称重复？）"
            if new_id > 0:
                write_audit_log(
                    action="SKILL_CREATE",
                    username=self.current_user,
                    target=f"skill:{new_id}",
                    detail=f"name={name}, type={skill_type}",
                    client_ip=self.request.remote_ip or "",
                )

        self.redirect(f"/admin/skill?msg={msg}")


class SkillDeleteHandler(AdminBaseHandler):
    """删除技能"""

    @tornado.web.authenticated
    def post(self):
        skill_id = int(self.get_body_argument("id", 0))
        skill = SkillRepository.get_by_id(skill_id)
        name = skill["name"] if skill else "unknown"
        SkillRepository.delete(skill_id)
        write_audit_log(
            action="SKILL_DELETE",
            username=self.current_user,
            target=f"skill:{skill_id}",
            detail=f"name={name}",
            client_ip=self.request.remote_ip or "",
        )
        self.redirect("/admin/skill?msg=已删除")


class SkillToggleHandler(AdminBaseHandler):
    """启用/禁用技能"""

    @tornado.web.authenticated
    def post(self):
        skill_id = int(self.get_body_argument("id", 0))
        status = SkillRepository.toggle_enabled(skill_id)
        if status == -1:
            self.write('<script>alert("技能不存在");window.history.back();</script>')
        else:
            write_audit_log(
                action="SKILL_TOGGLE",
                username=self.current_user,
                target=f"skill:{skill_id}",
                detail=f"status={'启用' if status == 1 else '禁用'}",
                client_ip=self.request.remote_ip or "",
            )
            self.redirect("/admin/skill?msg=状态已更新")
