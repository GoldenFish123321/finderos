"""
function.py �?functions 表的仓储对象

采用 Repository 模式，提供功能的 CRUD 操作�?功能采用树形结构（一�?二级），通过 parent_id 自引用�?"""

from app.models.db import get_db


class FunctionRepository:
    """功能数据访问�?""

    @staticmethod
    def get_all(page: int = 1, page_size: int = 20) -> tuple:
        """分页查询所有功能，返回 (rows, total)�?""
        with get_db() as conn:
            total = conn.execute("SELECT COUNT(*) as cnt FROM functions").fetchone()["cnt"]
            rows = conn.execute(
                "SELECT * FROM functions ORDER BY parent_id ASC, sort_order ASC, id ASC "
                "LIMIT ? OFFSET ?",
                (page_size, (page - 1) * page_size),
            ).fetchall()
        return rows, total

    @staticmethod
    def get_tree() -> list:
        """获取功能树形结构（用�?Layui tree 组件）�?""
        with get_db() as conn:
            all_funcs = conn.execute(
                "SELECT * FROM functions ORDER BY sort_order ASC, id ASC"
            ).fetchall()

        # 构建树：单次遍历，使用独�?node_map 避免子节点丢�?        node_map = {}
        tree = []
        for row in all_funcs:
            node = {
                "id": row["id"],
                "title": f'{row["icon"]} {row["name"]}' if row["icon"] else row["name"],
                "spread": True,
                "href": row["route_path"] if row["route_path"] else "",
                "children": [],
            }
            node_map[row["id"]] = node

            if row["parent_id"] is None:
                tree.append(node)
            elif row["parent_id"] in node_map:
                node_map[row["parent_id"]]["children"].append(node)

        # 移除�?children
        def clean_children(nodes):
            for n in nodes:
                if not n["children"]:
                    del n["children"]
                else:
                    clean_children(n["children"])

        clean_children(tree)
        return tree

    @staticmethod
    def get_enabled_tree(role_id: int = None) -> list:
        """获取启用的功能树，可选标记角色已拥有的功能�?""
        with get_db() as conn:
            all_funcs = conn.execute(
                "SELECT * FROM functions WHERE is_enabled = 1 ORDER BY sort_order ASC, id ASC"
            ).fetchall()

        checked_ids = set()
        if role_id:
            rows = conn.execute(
                "SELECT function_id FROM role_functions WHERE role_id = ?", (role_id,)
            ).fetchall()
            checked_ids = {r["function_id"] for r in rows}

        # 单次遍历构建树，避免子节点丢�?        node_map = {}
        tree = []
        for row in all_funcs:
            node = {
                "id": row["id"],
                "title": f'<i class="layui-icon {row["icon"]}"></i> {row["name"]}',
                "spread": True,
                "checked": row["id"] in checked_ids,
                "children": [],
            }
            node_map[row["id"]] = node
            if row["parent_id"] is None:
                tree.append(node)
            elif row["parent_id"] in node_map:
                node_map[row["parent_id"]]["children"].append(node)

        def clean_children(nodes):
            for n in nodes:
                if not n["children"]:
                    del n["children"]
                else:
                    clean_children(n["children"])

        clean_children(tree)
        return tree

    @staticmethod
    def get_by_id(func_id: int):
        """根据 ID 查询功能�?""
        with get_db() as conn:
            return conn.execute(
                "SELECT * FROM functions WHERE id = ?", (func_id,)
            ).fetchone()

    @staticmethod
    def get_parent_options() -> list:
        """获取可作为父级的功能列表（仅一级功能）�?""
        with get_db() as conn:
            return conn.execute(
                "SELECT id, name FROM functions WHERE parent_id IS NULL AND is_enabled = 1 "
                "ORDER BY sort_order ASC"
            ).fetchall()

    @staticmethod
    def create(name: str, icon: str = "", route_path: str = "",
               parent_id: int | None = None, sort_order: int = 0) -> int:
        """创建新功能，返回�?ID�?""
        with get_db() as conn:
            cur = conn.execute(
                "INSERT INTO functions (name, icon, route_path, parent_id, sort_order) "
                "VALUES (?, ?, ?, ?, ?)",
                (name.strip(), icon.strip(), route_path.strip(),
                 parent_id if parent_id else None, sort_order),
            )
            conn.commit()
            return cur.lastrowid

    @staticmethod
    def update(func_id: int, name: str, icon: str = "", route_path: str = "",
               parent_id: int | None = None, sort_order: int = 0) -> bool:
        """更新功能信息�?""
        with get_db() as conn:
            conn.execute(
                "UPDATE functions SET name=?, icon=?, route_path=?, parent_id=?, sort_order=? "
                "WHERE id=?",
                (name.strip(), icon.strip(), route_path.strip(),
                 parent_id if parent_id else None, sort_order, func_id),
            )
            conn.commit()
            return conn.total_changes > 0

    @staticmethod
    def delete(func_id: int) -> bool:
        """删除功能�?""
        with get_db() as conn:
            # 删除子功�?            conn.execute("DELETE FROM functions WHERE parent_id = ?", (func_id,))
            conn.execute("DELETE FROM functions WHERE id = ?", (func_id,))
            conn.commit()
            return conn.total_changes > 0

    @staticmethod
    def toggle_enabled(func_id: int) -> int:
        """切换功能的启�?禁用状态，返回新状�?(0/1)�?""
        with get_db() as conn:
            row = conn.execute(
                "SELECT is_enabled FROM functions WHERE id = ?", (func_id,)
            ).fetchone()
            if not row:
                return -1
            new_status = 0 if row["is_enabled"] == 1 else 1
            conn.execute(
                "UPDATE functions SET is_enabled = ? WHERE id = ?", (new_status, func_id)
            )
            # 如果是禁用，清除所有角色对该功能的关联
            if new_status == 0:
                conn.execute(
                    "DELETE FROM role_functions WHERE function_id = ?", (func_id,)
                )
            conn.commit()
            return new_status

    @staticmethod
    def get_count() -> int:
        """获取功能总数�?""
        with get_db() as conn:
            return conn.execute("SELECT COUNT(*) as cnt FROM functions").fetchone()["cnt"]
