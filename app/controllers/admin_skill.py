"""
admin_skill.py — 技能管理控制器

管理员管理技能库（新增/编辑/删除/启用禁用/分页）。
技能统一为 Prompt 模板，在模板中直接描述 MCP 工具用法。
v0.10: 支持绑定 MCP 工具（mcp_tool_id）。
"""
import tornado.web
from app.controllers.admin_base import AdminBaseHandler
from app.models.skill import SkillRepository
from app.models.mcp_tool import MCPToolRepository
from app.utils.security import write_audit_log


class SkillListHandler(AdminBaseHandler):
    """技能列表页"""

    @tornado.web.authenticated
    def get(self):
        try:
            page = max(1, int(self.get_query_argument("page", 1)))
        except (ValueError, TypeError):
            page = 1
        rows, total = SkillRepository.get_all(page=page, page_size=20)
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
            # v0.10: 加载启用的 MCP 工具列表供绑定选择
            mcp_tools=MCPToolRepository.get_enabled(),
        )

    @tornado.web.authenticated
    def post(self):
        skill_id = self.get_body_argument("id", None)
        name = self.get_body_argument("name", "").strip()
        description = self.get_body_argument("description", "").strip()
        prompt_template = self.get_body_argument("prompt_template", "").strip()
        # v0.10: 读取 mcp_tool_id（允许为空表示纯 prompt 型 Skill）
        mcp_tool_id_str = self.get_body_argument("mcp_tool_id", "").strip()
        mcp_tool_id = int(mcp_tool_id_str) if mcp_tool_id_str else None

        if not name:
            self.write('<script>alert("技能名称不能为空");window.history.back();</script>')
            return

        if skill_id:
            skill_id = int(skill_id)
            ok = SkillRepository.update(skill_id, name, description, prompt_template, mcp_tool_id)
            msg = "更新成功" if ok else "更新失败（名称重复？）"
            write_audit_log(
                action="SKILL_UPDATE",
                username=self.current_user,
                target=f"skill:{skill_id}",
                detail=f"name={name}",
                client_ip=self.request.remote_ip or "",
            )
        else:
            new_id = SkillRepository.create(name, description, prompt_template, mcp_tool_id)
            msg = "创建成功" if new_id > 0 else "创建失败（名称重复？）"
            if new_id > 0:
                write_audit_log(
                    action="SKILL_CREATE",
                    username=self.current_user,
                    target=f"skill:{new_id}",
                    detail=f"name={name}",
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
