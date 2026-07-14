"""
function.py - Functions table repository (Repository pattern)

Tree-structured (2-level) via parent_id self-reference.
"""
from app.models.db import get_db


class FunctionRepository:
    """Function data access class."""

    @staticmethod
    def get_all(page: int = 1, page_size: int = 20) -> tuple:
        """Paginated query of all functions. Returns (rows, total)."""
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
        """Get function tree structure (for Layui tree component)."""
        with get_db() as conn:
            all_funcs = conn.execute(
                "SELECT * FROM functions ORDER BY sort_order ASC, id ASC"
            ).fetchall()

        # 第一遍：创建所有节点放入 node_map，收集顶层节点
        node_map = {}
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

        # 第二遍：建立父子关系（确保父节点无论顺序都已被创建）
        for row in all_funcs:
            if row["parent_id"] is None:
                tree.append(node_map[row["id"]])
            elif row["parent_id"] in node_map:
                node_map[row["parent_id"]]["children"].append(node_map[row["id"]])

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
        """Get enabled function tree, optionally marking role-owned functions."""
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

        # 第一遍：创建所有节点放入 node_map
        node_map = {}
        for row in all_funcs:
            node = {
                "id": row["id"],
                "title": f'<i class="layui-icon {row["icon"]}"></i> {row["name"]}',
                "spread": True,
                "checked": row["id"] in checked_ids,
                "children": [],
            }
            node_map[row["id"]] = node

        # 第二遍：建立父子关系（确保父节点无论顺序都已被创建）
        tree = []
        for row in all_funcs:
            if row["parent_id"] is None:
                tree.append(node_map[row["id"]])
            elif row["parent_id"] in node_map:
                node_map[row["parent_id"]]["children"].append(node_map[row["id"]])

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
        """Get function by ID."""
        with get_db() as conn:
            return conn.execute(
                "SELECT * FROM functions WHERE id = ?", (func_id,)
            ).fetchone()

    @staticmethod
    def get_parent_options() -> list:
        """Get available parent functions (top-level only)."""
        with get_db() as conn:
            return conn.execute(
                "SELECT id, name FROM functions WHERE parent_id IS NULL AND is_enabled = 1 "
                "ORDER BY sort_order ASC"
            ).fetchall()

    @staticmethod
    def create(name: str, icon: str = "", route_path: str = "",
               parent_id: int | None = None, sort_order: int = 0) -> int:
        """Create a new function. Returns new ID."""
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
        """Update function info."""
        with get_db() as conn:
            cursor = conn.execute(
                "UPDATE functions SET name=?, icon=?, route_path=?, parent_id=?, sort_order=? "
                "WHERE id=?",
                (name.strip(), icon.strip(), route_path.strip(),
                 parent_id if parent_id else None, sort_order, func_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    @staticmethod
    def delete(func_id: int) -> bool:
        """Delete a function and its children."""
        with get_db() as conn:
            conn.execute("DELETE FROM functions WHERE parent_id = ?", (func_id,))
            cursor = conn.execute("DELETE FROM functions WHERE id = ?", (func_id,))
            conn.commit()
            return cursor.rowcount > 0

    @staticmethod
    def toggle_enabled(func_id: int) -> int:
        """Toggle function enabled/disabled. Returns new status (0/1) or -1.
        
        禁用父功能时，同时清理所有子功能的 role_functions 关联，
        避免数据层面残留不一致的权限记录。
        """
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
            if new_status == 0:
                # 清理自身 role_functions 关联
                conn.execute(
                    "DELETE FROM role_functions WHERE function_id = ?", (func_id,)
                )
                # 清理所有子功能的 role_functions 关联（通过子查询找出所有子功能ID）
                conn.execute(
                    "DELETE FROM role_functions WHERE function_id IN "
                    "(SELECT id FROM functions WHERE parent_id = ?)",
                    (func_id,),
                )
            conn.commit()
            return new_status

    @staticmethod
    def get_count() -> int:
        """Get total function count."""
        with get_db() as conn:
            return conn.execute("SELECT COUNT(*) as cnt FROM functions").fetchone()["cnt"]

    @staticmethod
    def get_siblings(parent_id: int | None) -> list:
        """获取同级兄弟节点，按 sort_order 排序。"""
        with get_db() as conn:
            if parent_id is None:
                return conn.execute(
                    "SELECT id, name, sort_order FROM functions "
                    "WHERE parent_id IS NULL ORDER BY sort_order ASC, id ASC"
                ).fetchall()
            else:
                return conn.execute(
                    "SELECT id, name, sort_order FROM functions "
                    "WHERE parent_id = ? ORDER BY sort_order ASC, id ASC",
                    (parent_id,),
                ).fetchall()

    @staticmethod
    def swap_sort(id_a: int, id_b: int, sort_a: int, sort_b: int):
        """交换两个功能的 sort_order 值。"""
        with get_db() as conn:
            conn.execute("UPDATE functions SET sort_order = ? WHERE id = ?", (sort_b, id_a))
            conn.execute("UPDATE functions SET sort_order = ? WHERE id = ?", (sort_a, id_b))
            conn.commit()
