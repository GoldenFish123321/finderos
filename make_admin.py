#!/usr/bin/env python3
"""
make_admin.py — 管理员账号创建工具

独立的命令行脚本，用于快速创建/重置管理员账号。
无需启动 Web 服务即可操作。

用法:
    python make_admin.py                           # 交互式创建
    python make_admin.py --username admin --password admin888  # 命令行创建
    python make_admin.py --username admin --password admin888 --role-id 1  # 指定角色
    python make_admin.py --list                    # 列出所有用户
    python make_admin.py --reset --username admin --password newpass  # 重置密码

借鉴自盾御-肖逸飞项目的 make_admin.py 设计。
"""

import argparse
import hashlib
import os
import secrets
import sys

# 确保可以导入 app 模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.config.settings import settings
from app.models.db import init_db, get_db

# 默认角色 ID：1=系统管理员, 2=普通用户
DEFAULT_ADMIN_ROLE_ID = 1


def hash_password(password: str) -> tuple[str, str]:
    """使用 PBKDF2-SHA256 哈希密码，返回 (hash_hex, salt_hex)。"""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, settings.PBKDF2_ITERATIONS)
    return dk.hex(), salt.hex()


def create_admin(username: str, password: str, role_id: int = DEFAULT_ADMIN_ROLE_ID):
    """创建管理员账号。"""
    init_db()

    with get_db() as conn:
        # 检查角色是否存在
        role = conn.execute("SELECT id, name FROM roles WHERE id = ?", (role_id,)).fetchone()
        if not role:
            print(f"错误: 角色 ID={role_id} 不存在")
            print("可用角色:")
            roles = conn.execute("SELECT id, name FROM roles").fetchall()
            for r in roles:
                print(f"  ID={r['id']}: {r['name']}")
            sys.exit(1)

        # 检查用户是否已存在
        existing = conn.execute(
            "SELECT id, username FROM users WHERE username = ?", (username,)
        ).fetchone()

        password_hash, salt = hash_password(password)

        if existing:
            print(f"用户 '{username}' 已存在 (ID={existing['id']})，正在更新密码...")
            conn.execute(
                "UPDATE users SET password_hash = ?, salt = ?, role_id = ? WHERE id = ?",
                (password_hash, salt, role_id, existing["id"]),
            )
            print(f"✅ 密码已更新")
        else:
            conn.execute(
                "INSERT INTO users (username, password_hash, salt, role_id, is_enabled) "
                "VALUES (?, ?, ?, ?, 1)",
                (username, password_hash, salt, role_id),
            )
            print(f"✅ 管理员 '{username}' 创建成功，角色: {role['name']}")

        print(f"   用户名: {username}")
        print(f"   角色: {role['name']}")
        print(f"   密码迭代次数: {settings.PBKDF2_ITERATIONS:,}")


def list_users():
    """列出所有用户。"""
    init_db()
    with get_db() as conn:
        users = conn.execute("""
            SELECT u.id, u.username, r.name as role_name, u.is_enabled, u.created_at
            FROM users u
            LEFT JOIN roles r ON u.role_id = r.id
            ORDER BY u.id
        """).fetchall()

        if not users:
            print("暂无用户")
            return

        print(f"{'ID':<5} {'用户名':<20} {'角色':<15} {'状态':<8} {'创建时间'}")
        print("-" * 80)
        for u in users:
            status = "启用" if u["is_enabled"] else "禁用"
            print(f"{u['id']:<5} {u['username']:<20} {u['role_name'] or '-':<15} {status:<8} {u['created_at']}")


def main():
    parser = argparse.ArgumentParser(
        description="瞭望与问数系统 — 管理员账号创建工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python make_admin.py --username admin --password MySecurePass123
  python make_admin.py --list
  python make_admin.py --reset --username admin --password NewPass456
        """,
    )
    parser.add_argument("--username", "-u", help="用户名")
    parser.add_argument("--password", "-p", help="密码")
    parser.add_argument("--role-id", type=int, default=DEFAULT_ADMIN_ROLE_ID,
                        help=f"角色 ID（默认: {DEFAULT_ADMIN_ROLE_ID}=系统管理员, 2=普通用户）")
    parser.add_argument("--list", "-l", action="store_true", help="列出所有用户")
    parser.add_argument("--reset", "-r", action="store_true", help="重置已有用户密码")

    args = parser.parse_args()

    if args.list:
        list_users()
        return

    username = args.username
    password = args.password

    # 交互式输入
    if not username:
        username = input("用户名: ").strip()
    if not password:
        import getpass
        password = getpass.getpass("密码: ").strip()
        confirm = getpass.getpass("确认密码: ").strip()
        if password != confirm:
            print("错误: 两次密码不一致")
            sys.exit(1)

    if not username or not password:
        print("错误: 用户名和密码不能为空")
        sys.exit(1)

    if len(username) < 3 or len(username) > 32:
        print("错误: 用户名长度应在 3-32 个字符之间")
        sys.exit(1)

    if len(password) < 8:
        print("错误: 密码长度至少 8 个字符")
        sys.exit(1)

    create_admin(username, password, args.role_id)


if __name__ == "__main__":
    main()
