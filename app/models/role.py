"""
role.py �?roles 表的仓储对象

采用 Repository 模式，提供角色的 CRUD 操作�?"""

import sqlite3
from app.models.db import get_db


class RoleRepository:
    """角色数据访问�?""

    @staticmethod
    def get_all(page: int = 1, page_size: int = 20) -> tuple:
        """分页查询所有角色，返回 (rows, total)�?""
        with get_db() as conn:
            total = conn.execute("SELECT COUNT(*) as cnt FROM roles").fetchone()["cnt"]
            rows = conn.execute(
                "SELECT * FROM roles ORDER BY is_system DESC, id ASC "
                "LIMIT ? OFFSET ?",
                (page_size, (page - 1) * page_size),
            ).fetchall()
        return rows, total

    @staticmethod
    def get_by_id(role_id: int):
        """根据 ID 查询角色�?""
        with get_db() as conn:
            return conn.execute(
                "SELECT * FROM roles WHERE id = ?", (role_id,)
            ).fetchone()

    @staticmethod
    def get_by_name(name: str):
        """根据名称查询角色�?""
        with get_db() as conn:
            return conn.execute(
                "SELECT * FROM roles WHERE name = ?", (name,)
            ).fetchone()

    @staticmethod
    def create(name: str, description: str = "") -> bool:
        """创建新角色，返回 True 成功 / False 名称重复�?""
        try:
            with get_db() as conn:
                conn.execute(
                    "INSERT INTO roles (name, description) VALUES (?, ?)",
                    (name.strip(), description.strip()),
                )
                conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    @staticmethod
    def update(role_id: int, name: str, description: str = "") -> bool:
        """更新角色信息�?""
        try:
            with get_db() as conn:
                conn.execute(
                    "UPDATE roles SET name = ?, description = ? WHERE id = ?",
                    (name.strip(), description.strip(), role_id),
                )
                conn.commit()
            return conn.total_changes > 0
        except sqlite3.IntegrityError:
            return False

    @staticmethod
    def delete(role_id: int) -> bool:
        """删除角色（系统角色不可删除）�?""
        with get_db() as conn:
            # 检查是否系统角�?            row = conn.execute(
                "SELECT is_system FROM roles WHERE id = ?", (role_id,)
            ).fetchone()
            if not row or row["is_system"] == 1:
                return False
            # 解除该角色关联的用户
            conn.execute(
                "UPDATE users SET role_id = NULL WHERE role_id = ?", (role_id,)
            )
            conn.execute("DELETE FROM roles WHERE id = ?", (role_id,))
            conn.commit()
        return True

    @staticmethod
    def get_count() -> int:
        """获取角色总数�?""
        with get_db() as conn:
            return conn.execute("SELECT COUNT(*) as cnt FROM roles").fetchone()["cnt"]

    @staticmethod
    def get_function_ids(role_id: int) -> list:
        """获取角色关联的功�?ID 列表�?""
        with get_db() as conn:
            rows = conn.execute(
                "SELECT function_id FROM role_functions WHERE role_id = ?",
                (role_id,),
            ).fetchall()
        return [r["function_id"] for r in rows]

    @staticmethod
    def set_functions(role_id: int, function_ids: list[int]):
        """设置角色关联的功能（全量替换）�?""
        with get_db() as conn:
            conn.execute(
                "DELETE FROM role_functions WHERE role_id = ?", (role_id,)
            )
            conn.executemany(
                "INSERT INTO role_functions (role_id, function_id) VALUES (?, ?)",
                [(role_id, fid) for fid in function_ids],
            )
            conn.commit()
