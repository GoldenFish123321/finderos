## 问题描述

`app/models/db.py` 中的 `init_db()` 函数已经膨胀为一个"超级函数"，包含：

1. **建表语句**：`users`, `roles`, `functions`, `role_functions`, `watch_sources`, `watch_results`, `ai_models`, `data_warehouse`, `digital_employees`, `skills`, `audit_logs`, `conversations`, `conversation_messages` 等十余张表
2. **内联迁移**：直接在 `init_db()` 中用 try/except 包裹 `ALTER TABLE ADD COLUMN` 语句
3. **索引创建**：`CREATE INDEX IF NOT EXISTS` 等
4. **FTS5 虚拟表**：`CREATE VIRTUAL TABLE ... USING fts5` + 同步触发器
5. **种子数据**：通过 `seed_default_data()` 插入默认角色、用户、功能、菜单、模型、员工等

## 具体问题

1. **无法版本化管理**：不知道当前数据库处于哪个 schema 版本
2. **迁移不可逆**：`ALTER TABLE ADD COLUMN` 无法回滚
3. **try/except 吞异常**：迁移失败只打日志不中断，可能留下半迁移状态
4. **建表和迁移混在一起**：新建数据库和升级已有数据库走同一代码路径
5. **测试困难**：无法单独测试某条迁移

## 建议修复

引入数据库迁移机制（如使用简单的手动迁移脚本，或不引入第三方依赖自己维护迁移记录表）：

```python
# 方案：迁移记录表 + 版本号
def run_migrations():
    current_version = get_db_version()  # 从 _migrations 表读取
    migrations = [
        (1, "create_users_table", "CREATE TABLE ..."),
        (2, "add_total_tokens", "ALTER TABLE ..."),
        # ...
    ]
    for version, name, sql in migrations:
        if version > current_version:
            execute_migration(version, name, sql)
```

或直接引入 Alembic/SQLAlchemy-Migrate 等成熟工具。
