"""
admin_menu.py — 菜单管理控制器

菜单管理允许预览和排序角色关联的功能形成的左侧菜单。
数据来源：角色+功能的映射表。

v0.2.12: 新增菜单排序（上移/下移）功能，借鉴冯凯乐项目的拖拽排序思路。
"""

import json
import tornado.web
from app.controllers.admin_base import AdminBaseHandler
from app.models.role import RoleRepository
from app.models.function import FunctionRepository
from app.utils.security import sanitize_html


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
            try:
                role_id_int = int(role_id)
            except (ValueError, TypeError):
                self.write('<script>alert("无效的角色ID");window.history.back();</script>')
                return
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
                        "title": sanitize_html(row["name"]),
                        "icon": sanitize_html(row["icon"]),
                        "href": sanitize_html(row["route_path"]),
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
            xsrf_token=self.xsrf_token.decode() if isinstance(self.xsrf_token, bytes) else self.xsrf_token,
        )


class MenuSortHandler(AdminBaseHandler):
    """菜单排序处理器（上移/下移），借鉴冯凯乐项目的菜单排序设计"""

    @tornado.web.authenticated
    def post(self):
        try:
            func_id = int(self.get_body_argument("id", 0))
        except (ValueError, TypeError):
            self.write({"code": 1, "msg": "无效的功能ID"})
            return
        direction = self.get_body_argument("direction", "up")  # "up" or "down"

        if not func_id:
            self.write({"code": 1, "msg": "参数错误"})
            return

        # 获取当前功能
        current = FunctionRepository.get_by_id(func_id)
        if not current:
            self.write({"code": 1, "msg": "功能不存在"})
            return

        parent_id = current["parent_id"]
        current_sort = current["sort_order"]

        # 获取同级兄弟节点
        siblings = FunctionRepository.get_siblings(parent_id)

        if direction == "up":
            # 找到比当前 sort_order 小的最大者
            target = None
            for s in siblings:
                if s["sort_order"] < current_sort:
                    if target is None or s["sort_order"] > target["sort_order"]:
                        target = s
        else:  # down
            # 找到比当前 sort_order 大的最小者
            target = None
            for s in siblings:
                if s["sort_order"] > current_sort:
                    if target is None or s["sort_order"] < target["sort_order"]:
                        target = s

        if not target:
            self.write({"code": 1, "msg": "已到边界，无法继续移动"})
            return

        # 交换 sort_order
        FunctionRepository.swap_sort(func_id, target["id"], current_sort, target["sort_order"])
        self.write({"code": 0, "msg": f"已{'上移' if direction == 'up' else '下移'}"})
