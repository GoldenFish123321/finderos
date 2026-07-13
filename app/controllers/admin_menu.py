"""
admin_menu.py — 菜单管理控制器

菜单管理允许预览和排序角色关联的功能形成的左侧菜单。
数据来源：角色+功能的映射表。
"""

import tornado.web
from app.controllers.admin_base import AdminBaseHandler
from app.models.role import RoleRepository
from app.models.function import FunctionRepository


class MenuHandler(AdminBaseHandler):
    """菜单管理页"""

    @tornado.web.authenticated
    def get(self):
        role_id = self.get_query_argument("role_id", None)
        roles = RoleRepository.get_all(page=1, page_size=100)[0]

        # 默认选第一个角色
        if not role_id and roles:
            role_id = str(roles[0]["id"])

        menu_tree = []
        selected_role = None
        if role_id:
            role_id_int = int(role_id)
            selected_role = RoleRepository.get_by_id(role_id_int)
            # 获取该角色关联的功能树
            func_ids = RoleRepository.get_function_ids(role_id_int)
            all_funcs = FunctionRepository.get_all(page=1, page_size=1000)[0]

            # 构建树：只包含角色拥有的功能
            func_map = {}
            for row in all_funcs:
                if row["id"] in func_ids and row["is_enabled"] == 1:
                    func_map[row["id"]] = {
                        "id": row["id"],
                        "title": row["name"],
                        "icon": row["icon"],
                        "href": row["route_path"],
                        "sort": row["sort_order"],
                        "parent_id": row["parent_id"],
                        "children": [],
                    }

            for node in func_map.values():
                if node["parent_id"] is None:
                    menu_tree.append(node)
                elif node["parent_id"] in func_map:
                    func_map[node["parent_id"]]["children"].append(node)

            # 排序并清理空 children
            def clean(nodes):
                nodes.sort(key=lambda x: x["sort"])
                for n in nodes:
                    if not n["children"]:
                        del n["children"]
                    else:
                        clean(n["children"])
            clean(menu_tree)

        self.render(
            "admin/menu.html",
            title="菜单管理 — 瞭望与问数系统",
            username=self.current_user,
            roles=roles,
            selected_role=selected_role,
            selected_role_id=role_id,
            menu_tree=menu_tree,
        )
