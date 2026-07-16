"""
db.py - Database connection and initialization

Provides SQLite connection management and auto-table creation.
Database file: database/finderos.db
"""

import logging
import os
import sqlite3
from contextlib import contextmanager

from app.config.settings import settings

logger = logging.getLogger(__name__)

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "database")
DB_PATH = settings.DB_PATH if os.path.isabs(settings.DB_PATH) else os.path.join(DB_DIR, os.path.basename(settings.DB_PATH))


def _dict_factory(cursor, row):
    """Row factory that returns dicts instead of sqlite3.Row.

    Dicts support .get() with default values, which sqlite3.Row does not.
    This prevents AttributeError: 'sqlite3.Row' object has no attribute 'get'.
    """
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


def get_connection() -> sqlite3.Connection:
    """Get a new database connection. Caller is responsible for closing."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = _dict_factory
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")  # 5秒超时，避免并发写入 SQLITE_BUSY
    return conn


@contextmanager
def get_db():
    """Context manager for database connections. Auto-commits and closes on exit."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Initialize database: create all tables if not exist."""
    os.makedirs(DB_DIR, exist_ok=True)
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt          TEXT NOT NULL,
                role_id       INTEGER DEFAULT NULL,
                is_enabled    INTEGER DEFAULT 1,
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (role_id) REFERENCES roles(id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS roles (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT UNIQUE NOT NULL,
                description TEXT DEFAULT '',
                is_system   INTEGER DEFAULT 0,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS functions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                icon        TEXT DEFAULT '',
                route_path  TEXT DEFAULT '',
                parent_id   INTEGER DEFAULT NULL,
                sort_order  INTEGER DEFAULT 0,
                is_enabled  INTEGER DEFAULT 1,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (parent_id) REFERENCES functions(id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS role_functions (
                role_id     INTEGER NOT NULL,
                function_id INTEGER NOT NULL,
                PRIMARY KEY (role_id, function_id),
                FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE,
                FOREIGN KEY (function_id) REFERENCES functions(id) ON DELETE CASCADE
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS watch_sources (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                name            TEXT NOT NULL,
                description     TEXT DEFAULT '',
                url_template    TEXT NOT NULL,
                request_headers TEXT DEFAULT '{}',
                is_enabled      INTEGER DEFAULT 1,
                sort_order      INTEGER DEFAULT 0,
                schedule_interval INTEGER DEFAULT 0,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS watch_results (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id       INTEGER,
                keyword         TEXT DEFAULT '',
                request_url     TEXT DEFAULT '',
                response_status INTEGER DEFAULT 0,
                response_size   INTEGER DEFAULT 0,
                result_data     TEXT DEFAULT '',
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (source_id) REFERENCES watch_sources(id) ON DELETE SET NULL
            )
        """)
        # URL 去重索引（非空 URL 唯一，避免并发采集重复入库）
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_wr_url "
            "ON watch_results(request_url) WHERE request_url != ''"
        )

        conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_models (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                name            TEXT NOT NULL,
                provider        TEXT DEFAULT 'openai',
                api_base        TEXT DEFAULT '',
                api_key         TEXT DEFAULT '',
                model_name      TEXT DEFAULT '',
                category        TEXT DEFAULT 'text',
                system_prompt   TEXT DEFAULT '',
                temperature     REAL DEFAULT 0.7,
                top_p           REAL DEFAULT 1.0,
                top_k           INTEGER DEFAULT 50,
                max_tokens      INTEGER DEFAULT 4096,
                context_size    INTEGER DEFAULT 8192,
                total_tokens    INTEGER DEFAULT 0,
                is_enabled      INTEGER DEFAULT 1,
                is_default      INTEGER DEFAULT 0,
                model_scope     TEXT DEFAULT 'admin',
                owner_username  TEXT DEFAULT '',
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 兼容旧表迁移：模型分组。admin=管理员提供的全局模型；user=用户自助配置模型。
        try:
            cols = {row["name"] for row in conn.execute("PRAGMA table_info(ai_models)").fetchall()}
            if "model_scope" not in cols:
                conn.execute("ALTER TABLE ai_models ADD COLUMN model_scope TEXT DEFAULT 'admin'")
                logger.info("Database migration: added model_scope column to ai_models")
            if "owner_username" not in cols:
                conn.execute("ALTER TABLE ai_models ADD COLUMN owner_username TEXT DEFAULT ''")
                logger.info("Database migration: added owner_username column to ai_models")
            conn.execute(
                "UPDATE ai_models SET model_scope = 'admin' "
                "WHERE model_scope IS NULL OR model_scope = ''"
            )
            conn.execute(
                "UPDATE ai_models SET owner_username = '' "
                "WHERE owner_username IS NULL"
            )
        except Exception as e:
            logger.error(f"Database migration failed (ai_models scope): {e}", exc_info=True)

        # 兼容旧表迁移：为已存在的 ai_models 表添加 total_tokens 列
        try:
            cols = {row["name"] for row in conn.execute("PRAGMA table_info(ai_models)").fetchall()}
            if "total_tokens" not in cols:
                conn.execute("ALTER TABLE ai_models ADD COLUMN total_tokens INTEGER DEFAULT 0")
                logger.info("Database migration: added total_tokens column to ai_models")
        except Exception as e:
            logger.error(f"Database migration failed (ai_models.total_tokens): {e}", exc_info=True)

        # 兼容旧表迁移：为已存在的 watch_sources 表添加 schedule_interval 列 (v0.6)
        try:
            cols = {row["name"] for row in conn.execute("PRAGMA table_info(watch_sources)").fetchall()}
            if "schedule_interval" not in cols:
                conn.execute("ALTER TABLE watch_sources ADD COLUMN schedule_interval INTEGER DEFAULT 0")
                logger.info("Database migration: added schedule_interval column to watch_sources")
        except Exception as e:
            logger.error(f"Database migration failed (watch_sources.schedule_interval): {e}", exc_info=True)

        # 独立数据仓库表（v0.2 新增，借鉴郭家琪项目的独立设计）
        conn.execute("""
            CREATE TABLE IF NOT EXISTS data_warehouse (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                result_id           INTEGER DEFAULT NULL,
                title               TEXT DEFAULT '',
                link                TEXT DEFAULT '',
                summary             TEXT DEFAULT '',
                source_name         TEXT DEFAULT '',
                raw_data            TEXT DEFAULT '',
                is_deep_collected   INTEGER DEFAULT 0,
                deep_collected_at   TIMESTAMP DEFAULT NULL,
                created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (result_id) REFERENCES watch_results(id) ON DELETE SET NULL
            )
        """)
        # link 唯一索引用于去重
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_dw_link ON data_warehouse(link) WHERE link != ''")
        # 无 link 记录去重：title + source_name 组合唯一（防止并发竞态写入重复数据）
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_dw_title_source "
            "ON data_warehouse(title, source_name) WHERE (link IS NULL OR link = '')"
        )

        # FTS5 全文检索虚拟表（v0.3 — 智能问数增强）
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS data_warehouse_fts USING fts5(
                title, summary, source_name, content=data_warehouse,
                content_rowid=id
            )
        """)
        # 触发器：INSERT 时同步到 FTS
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS dw_fts_insert AFTER INSERT ON data_warehouse
            BEGIN
                INSERT INTO data_warehouse_fts(rowid, title, summary, source_name)
                VALUES (new.id, new.title, new.summary, new.source_name);
            END
        """)
        # 触发器：DELETE 时从 FTS 移除
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS dw_fts_delete AFTER DELETE ON data_warehouse
            BEGIN
                INSERT INTO data_warehouse_fts(data_warehouse_fts, rowid, title, summary, source_name)
                VALUES ('delete', old.id, old.title, old.summary, old.source_name);
            END
        """)
        # 触发器：UPDATE 时同步 FTS
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS dw_fts_update AFTER UPDATE ON data_warehouse
            BEGIN
                INSERT INTO data_warehouse_fts(data_warehouse_fts, rowid, title, summary, source_name)
                VALUES ('delete', old.id, old.title, old.summary, old.source_name);
                INSERT INTO data_warehouse_fts(rowid, title, summary, source_name)
                VALUES (new.id, new.title, new.summary, new.source_name);
            END
        """)

        # 审计日志表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                action      TEXT NOT NULL,
                username    TEXT DEFAULT '',
                target      TEXT DEFAULT '',
                detail      TEXT DEFAULT '',
                client_ip   TEXT DEFAULT '',
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 技能库表 (v0.7 新增 — 技能管理模块)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS skills (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                name            TEXT UNIQUE NOT NULL,
                description     TEXT DEFAULT '',
                skill_type      TEXT NOT NULL DEFAULT 'prompt',
                prompt_template TEXT DEFAULT '',
                function_name   TEXT DEFAULT '',
                function_params TEXT DEFAULT '{}',
                is_enabled      INTEGER DEFAULT 1,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 接口管理表 (v0.9 新增)：可复用 API 接口模板，供 API 型数字员工联动选择
        conn.execute("""
            CREATE TABLE IF NOT EXISTS api_interfaces (
                id                       INTEGER PRIMARY KEY AUTOINCREMENT,
                name                     TEXT UNIQUE NOT NULL,
                description              TEXT DEFAULT '',
                api_url                  TEXT NOT NULL,
                api_method               TEXT DEFAULT 'GET',
                api_headers              TEXT DEFAULT '{}',
                api_params_template      TEXT DEFAULT '',
                response_render_template TEXT DEFAULT '',
                api_secret               TEXT DEFAULT '',
                is_enabled               INTEGER DEFAULT 1,
                sort_order               INTEGER DEFAULT 0,
                created_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 数字化员工表 (v0.4 新增)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS digital_employees (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                name                    TEXT NOT NULL,
                employee_type           TEXT NOT NULL DEFAULT 'llm',
                description             TEXT DEFAULT '',
                -- LLM 型字段
                model_id                INTEGER DEFAULT NULL,
                system_prompt           TEXT DEFAULT '',
                skills                  TEXT DEFAULT '[]',
                crawl4ai_enabled        INTEGER DEFAULT 0,
                mcp_tool_ids            TEXT DEFAULT '[]',
                -- API 型字段
                api_url                 TEXT DEFAULT '',
                api_method              TEXT DEFAULT 'GET',
                api_headers             TEXT DEFAULT '{}',
                api_params_template     TEXT DEFAULT '',
                response_render_template TEXT DEFAULT '',
                api_secret              TEXT DEFAULT '',
                api_interface_id        INTEGER DEFAULT NULL,
                -- 通用字段
                is_enabled              INTEGER DEFAULT 1,
                created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (model_id) REFERENCES ai_models(id) ON DELETE SET NULL,
                FOREIGN KEY (api_interface_id) REFERENCES api_interfaces(id) ON DELETE SET NULL
            )
        """)

        # 兼容旧表迁移：为已存在的 digital_employees 表添加 api_interface_id 列
        try:
            cols = {row["name"] for row in conn.execute("PRAGMA table_info(digital_employees)").fetchall()}
            if "api_interface_id" not in cols:
                conn.execute("ALTER TABLE digital_employees ADD COLUMN api_interface_id INTEGER DEFAULT NULL")
                logger.info("Database migration: added api_interface_id column to digital_employees")
        except Exception as e:
            logger.error(f"Database migration failed (digital_employees.api_interface_id): {e}", exc_info=True)

        # ── v1.2.0 用户表新增 face_descriptor 字段（人脸登录） ──
        try:
            cols = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
            if "face_descriptor" not in cols:
                conn.execute("ALTER TABLE users ADD COLUMN face_descriptor TEXT DEFAULT NULL")
                logger.info("Database migration: added face_descriptor column to users")
        except Exception as e:
            logger.error(f"Database migration failed (users.face_descriptor): {e}", exc_info=True)

        # 对话管理表 (v0.5 新增 — 多轮对话支持)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT DEFAULT '新对话',
                username    TEXT DEFAULT '',
                model_id    INTEGER DEFAULT NULL,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (model_id) REFERENCES ai_models(id) ON DELETE SET NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversation_messages (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                role            TEXT NOT NULL,
                content         TEXT DEFAULT '',
                token_count     INTEGER DEFAULT 0,
                is_sensitive    INTEGER DEFAULT 0,
                review_status   TEXT DEFAULT 'pending',
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_conv_msgs_conv ON conversation_messages(conversation_id)")
        # v1.3.5 Issue #18: 消息管理索引（先确保列存在再建索引）
        try:
            cols = {row["name"] for row in conn.execute("PRAGMA table_info(conversation_messages)").fetchall()}
            if "is_sensitive" not in cols:
                conn.execute("ALTER TABLE conversation_messages ADD COLUMN is_sensitive INTEGER DEFAULT 0")
                logger.info("Database migration: added is_sensitive column to conversation_messages")
            if "review_status" not in cols:
                conn.execute("ALTER TABLE conversation_messages ADD COLUMN review_status TEXT DEFAULT 'pending'")
                logger.info("Database migration: added review_status column to conversation_messages")
        except Exception as e:
            logger.error(f"Database migration failed (conversation_messages): {e}", exc_info=True)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_conv_msgs_sensitive ON conversation_messages(is_sensitive)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_conv_msgs_review ON conversation_messages(review_status)")

        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_role_id ON users(role_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_functions_parent ON functions(parent_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_role_functions_role ON role_functions(role_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_role_functions_func ON role_functions(function_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_watch_sources_enabled ON watch_sources(is_enabled)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_watch_results_source ON watch_results(source_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_models_default ON ai_models(is_default)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_models_scope_owner ON ai_models(model_scope, owner_username)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_api_interfaces_enabled ON api_interfaces(is_enabled)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_api_interfaces_name ON api_interfaces(name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_digital_employees_api_interface ON digital_employees(api_interface_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_username ON audit_logs(username)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_created ON audit_logs(created_at)")

        # ── v0.10 MCP 工具注册表 (数据库驱动) ──
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mcp_tools (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                name            TEXT UNIQUE NOT NULL,
                display_name    TEXT NOT NULL,
                description     TEXT DEFAULT '',
                category        TEXT DEFAULT 'general',
                tool_type       TEXT DEFAULT 'builtin',
                handler_module  TEXT DEFAULT '',
                api_url         TEXT DEFAULT '',
                api_method      TEXT DEFAULT 'GET',
                api_headers     TEXT DEFAULT '{}',
                api_params_template TEXT DEFAULT '',
                input_schema    TEXT DEFAULT '{}',
                output_schema   TEXT DEFAULT '{}',
                is_enabled      INTEGER DEFAULT 1,
                is_system       INTEGER DEFAULT 0,
                sort_order      INTEGER DEFAULT 0,
                config          TEXT DEFAULT '{}',
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ── v0.10 MCP 工具测试日志表 ──
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mcp_tool_test_logs (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                tool_id         INTEGER NOT NULL,
                test_params     TEXT DEFAULT '{}',
                test_result     TEXT DEFAULT '',
                is_success      INTEGER DEFAULT 0,
                duration_ms     INTEGER DEFAULT 0,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (tool_id) REFERENCES mcp_tools(id) ON DELETE CASCADE
            )
        """)

        # ── v0.10 skills 表新增 mcp_tool_id 列 ──
        try:
            cols = {row["name"] for row in conn.execute("PRAGMA table_info(skills)").fetchall()}
            if "mcp_tool_id" not in cols:
                conn.execute("ALTER TABLE skills ADD COLUMN mcp_tool_id INTEGER DEFAULT NULL REFERENCES mcp_tools(id) ON DELETE SET NULL")
                logger.info("Database migration: added mcp_tool_id column to skills")
        except Exception as e:
            logger.error(f"Database migration failed (skills.mcp_tool_id): {e}", exc_info=True)

        # ── v0.10 digital_employees 表新增 mcp_tool_ids 列 ──
        try:
            cols = {row["name"] for row in conn.execute("PRAGMA table_info(digital_employees)").fetchall()}
            if "mcp_tool_ids" not in cols:
                conn.execute("ALTER TABLE digital_employees ADD COLUMN mcp_tool_ids TEXT DEFAULT '[]'")
                logger.info("Database migration: added mcp_tool_ids column to digital_employees")
        except Exception as e:
            logger.error(f"Database migration failed (digital_employees.mcp_tool_ids): {e}", exc_info=True)

        # ── v1.6.0 digital_employees 表新增 mcp_tool_id 列（API 型员工绑定单个 MCP 工具）──
        try:
            cols = {row["name"] for row in conn.execute("PRAGMA table_info(digital_employees)").fetchall()}
            if "mcp_tool_id" not in cols:
                conn.execute("ALTER TABLE digital_employees ADD COLUMN mcp_tool_id INTEGER DEFAULT NULL REFERENCES mcp_tools(id) ON DELETE SET NULL")
                logger.info("Database migration: added mcp_tool_id column to digital_employees")
        except Exception as e:
            logger.error(f"Database migration failed (digital_employees.mcp_tool_id): {e}", exc_info=True)

        # ── v1.7.0 已有天气员工绑定 MCP 工具（迁移旧 HTTP 直连到 MCP 代理）──
        try:
            import json as _json
            # 确保 weather_query MCP 工具存在
            existing_tool = conn.execute(
                "SELECT id FROM mcp_tools WHERE name = ?", ("weather_query",)
            ).fetchone()
            if not existing_tool:
                cur = conn.execute(
                    "INSERT INTO mcp_tools (name, display_name, description, category, tool_type, "
                    "api_url, api_method, api_headers, input_schema, is_enabled, is_system, sort_order) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    ("weather_query", "天气查询",
                     "通过 wttr.in 免费 API 查询指定城市的实时天气信息，返回温度、天气状况、湿度、风力等数据。",
                     "general", "api",
                     "https://wttr.in/{message}?format=j1", "GET",
                     _json.dumps({"Accept": "application/json"}, ensure_ascii=False),
                     _json.dumps({
                         "type": "object",
                         "properties": {"message": {"type": "string", "description": "城市名称，如 Beijing、成都、London"}},
                         "required": ["message"]
                     }, ensure_ascii=False),
                     1, 0, 99),
                )
                weather_tool_id = cur.lastrowid
                logger.info("Database migration: created weather_query MCP tool")
            else:
                weather_tool_id = existing_tool["id"]

            # 更新已有天气员工绑定 MCP 工具
            updated = conn.execute(
                "UPDATE digital_employees SET mcp_tool_id = ? "
                "WHERE employee_type = 'api' AND name = ? AND mcp_tool_id IS NULL",
                (weather_tool_id, "天气")
            ).rowcount
            if updated:
                logger.info(f"Database migration: bound weather employee to MCP tool (weather_query), updated {updated} row(s)")
        except Exception as e:
            logger.error(f"Database migration failed (weather employee MCP binding): {e}", exc_info=True)

        # ── v0.11 系统配置表 (key-value) ──
        conn.execute("""
            CREATE TABLE IF NOT EXISTS system_config (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                key         TEXT UNIQUE NOT NULL,
                value       TEXT DEFAULT '',
                description TEXT DEFAULT '',
                category    TEXT DEFAULT 'general',
                updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_system_config_key ON system_config(key)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_system_config_category ON system_config(category)")

        # ── v1.2.0 舆情大屏（敏感词 + 预警） ──
        from app.models.sensitive_word import SensitiveWordRepository
        SensitiveWordRepository.init_table(conn)

        conn.commit()
        logger.info(f"Database initialized: {DB_PATH}")

        # ── v2.0 统一接口驱动架构: api_interfaces 新增字段 ──
        try:
            conn.execute("ALTER TABLE api_interfaces ADD COLUMN interface_type TEXT DEFAULT 'external'")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE api_interfaces ADD COLUMN is_system INTEGER DEFAULT 0")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE api_interfaces ADD COLUMN local_handler TEXT DEFAULT ''")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE api_interfaces ADD COLUMN response_content_type TEXT DEFAULT 'json'")
        except Exception:
            pass
        conn.commit()

        # ── v2.0 统一接口驱动架构: mcp_tools 新增字段 ──
        try:
            conn.execute("ALTER TABLE mcp_tools ADD COLUMN data_sources TEXT DEFAULT '[]'")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE mcp_tools ADD COLUMN transform_script TEXT DEFAULT ''")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE mcp_tools ADD COLUMN script_enabled INTEGER DEFAULT 0")
        except Exception:
            pass
        conn.commit()


def seed_default_data():
    """Seed default roles, admin account, and functions (idempotent)."""
    import hashlib
    import secrets

    with get_db() as conn:
        # 注意：不关闭外键约束，依赖插入顺序保证引用完整性
        # 先插入角色 → 再插入用户 → 再插入功能 → 最后关联

        existing = conn.execute("SELECT COUNT(*) as cnt FROM roles").fetchone()
        if existing["cnt"] == 0:
            conn.execute(
                "INSERT INTO roles (id, name, description, is_system) VALUES (?, ?, ?, ?)",
                (1, "系统管理员", "系统管理员角色，可访问后台管理系统所有功能", 1),
            )
            conn.execute(
                "INSERT INTO roles (id, name, description, is_system) VALUES (?, ?, ?, ?)",
                (2, "普通用户", "普通用户角色，可使用前台并默认配置模型 API", 1),
            )
            print("[种子] 默认角色已创建")

        existing_admin = conn.execute(
            "SELECT COUNT(*) as cnt FROM users WHERE username = ?", ("admin",)
        ).fetchone()
        if existing_admin["cnt"] == 0:
            salt = secrets.token_bytes(16)
            initial_password = settings.ADMIN_DEFAULT_PASSWORD or secrets.token_urlsafe(18)
            if len(initial_password) < 12:
                raise RuntimeError("ADMIN_DEFAULT_PASSWORD 必须至少 12 个字符")
            dk = hashlib.pbkdf2_hmac(
                "sha256", initial_password.encode(), salt, settings.PBKDF2_ITERATIONS
            )
            conn.execute(
                "INSERT INTO users (username, password_hash, salt, role_id, is_enabled) VALUES (?, ?, ?, ?, ?)",
                ("admin", dk.hex(), salt.hex(), 1, 1),
            )
            if settings.ADMIN_DEFAULT_PASSWORD:
                print("[种子] 默认管理员 admin 已创建（密码来自 ADMIN_DEFAULT_PASSWORD）")
            else:
                credential_path = DB_PATH + ".admin_initial_password"
                temp_credential_path = credential_path + f".{os.getpid()}.tmp"
                fd = os.open(temp_credential_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as credential_file:
                    credential_file.write(initial_password + "\n")
                os.replace(temp_credential_path, credential_path)
                print(f"[种子] 默认管理员 admin 已创建（一次性凭据文件: {credential_path}）")

        existing_funcs = conn.execute("SELECT COUNT(*) as cnt FROM functions").fetchone()
        if existing_funcs["cnt"] == 0:
            functions = [
                # 一级菜单
                (1, "系统总览", "layui-icon-console", "/admin", None, 1, 1),
                (2, "权限管理", "layui-icon-vercode", "", None, 2, 1),
                (3, "系统设置", "layui-icon-set", "", None, 3, 1),
                # 权限管理子项
                (4, "用户管理", "layui-icon-user", "/admin/user", 2, 1, 1),
                (5, "角色管理", "layui-icon-group", "/admin/role", 2, 2, 1),
                (6, "功能管理", "layui-icon-template-1", "/admin/function", 2, 3, 1),
                (7, "菜单管理", "layui-icon-list", "/admin/menu", 2, 4, 1),
                # 业务模块（一级）
                (8, "瞭望采集", "layui-icon-search", "/admin/watch", None, 4, 1),
                (9, "瞭源管理", "layui-icon-read", "/admin/watch/source", None, 5, 1),
                (10, "数据仓库", "layui-icon-component", "/admin/warehouse", None, 6, 1),
                (17, "采集日志", "layui-icon-list", "/admin/watch/log", None, 7, 1),
                (11, "模型引擎", "layui-icon-util", "/admin/model", None, 7, 1),
                (18, "会话管理", "layui-icon-dialogue", "/admin/conversation", None, 8, 1),
                (19, "模型 API 配置", "layui-icon-set", "/admin/model/config", None, 8, 1),
                # 系统设置子项（新增，借鉴陈子墨丰富的种子数据设计）
                (12, "AI对话", "layui-icon-dialogue", "/chat", 3, 1, 1),
                # 数字员工 (v0.4 新增)
                (13, "数字员工", "layui-icon-user", "/admin/employee", None, 9, 1),
                # 技能管理 (v0.7 新增)
                (14, "技能管理", "layui-icon-util", "/admin/skill", None, 10, 1),
                # MCP 工具管理 (v0.10 新增)
                (15, "MCP 工具管理", "layui-icon-component", "/admin/mcp/tool", None, 11, 1),
                # 接口管理 (v0.9 新增)
                (16, "接口管理", "layui-icon-link", "/admin/interface", None, 12, 1),
                # 常规设置 (v0.11 新增，归属系统设置父节点)
                (20, "常规设置", "layui-icon-set-fill", "/admin/config", 3, 2, 1),
                # 数智大屏 (v1.2.0 新增)
                (21, "数智大屏", "layui-icon-screen-full", "/admin/dashboard", None, 3, 1),
                # 舆情大屏 (v1.2.0 新增)
                (22, "舆情大屏", "layui-icon-log", "/admin/sentiment", None, 14, 1),
                # 消息管理 (v1.3.5 Issue #18 新增)
                (23, "消息管理", "layui-icon-email", "/admin/message", None, 15, 1),
            ]
            conn.executemany(
                "INSERT INTO functions (id, name, icon, route_path, parent_id, sort_order, is_enabled) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                functions,
            )
            print("[种子] 默认功能模块已创建")

        # 兼容旧数据库：补齐后续版本新增的功能节点并授权给系统管理员
        managed_func_ids = []
        for name, icon, route_path, parent_id, sort_order in (
            ("MCP 工具管理", "layui-icon-component", "/admin/mcp/tool", None, 10),
            ("接口管理", "layui-icon-link", "/admin/interface", None, 11),
            ("采集日志", "layui-icon-list", "/admin/watch/log", None, 7),
            ("会话管理", "layui-icon-dialogue", "/admin/conversation", None, 8),
            ("模型 API 配置", "layui-icon-set", "/admin/model/config", None, 8),
            ("常规设置", "layui-icon-set-fill", "/admin/config", 3, 2),
            ("数智大屏", "layui-icon-screen-full", "/admin/dashboard", None, 3),
            ("舆情大屏", "layui-icon-log", "/admin/sentiment", None, 14),
            ("消息管理", "layui-icon-email", "/admin/message", None, 15),
        ):
            func = conn.execute(
                "SELECT id FROM functions WHERE route_path = ?", (route_path,)
            ).fetchone()
            if not func:
                cur = conn.execute(
                    "INSERT INTO functions (name, icon, route_path, parent_id, sort_order, is_enabled) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (name, icon, route_path, parent_id, sort_order, 1),
                )
                func_id = cur.lastrowid
                print(f"[种子] {name}功能模块已补齐")
            else:
                func_id = func["id"]
            managed_func_ids.append(func_id)

        # 普通用户默认具备最小后台能力：配置模型 API。
        # 如需让普通用户默认管理 MCP 工具，可在此列表追加 "/admin/mcp/tool"。
        default_user_func_ids = []
        for route_path in ("/admin/model/config",):
            func = conn.execute(
                "SELECT id FROM functions WHERE route_path = ?", (route_path,)
            ).fetchone()
            if func:
                default_user_func_ids.append(func["id"])
        normal_role = conn.execute(
            "SELECT id FROM roles WHERE name = ?", ("普通用户",)
        ).fetchone()
        normal_role_id = normal_role["id"] if normal_role else 2

        existing_rf = conn.execute("SELECT COUNT(*) as cnt FROM role_functions").fetchone()
        if existing_rf["cnt"] == 0:
            func_ids = conn.execute("SELECT id FROM functions WHERE is_enabled = 1").fetchall()
            conn.executemany(
                "INSERT INTO role_functions (role_id, function_id) VALUES (?, ?)",
                [(1, row["id"]) for row in func_ids],
            )
            conn.executemany(
                "INSERT OR IGNORE INTO role_functions (role_id, function_id) VALUES (?, ?)",
                [(normal_role_id, func_id) for func_id in default_user_func_ids],
            )
            print("[种子] 管理员角色功能关联已创建")
        else:
            for func_id in managed_func_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO role_functions (role_id, function_id) VALUES (?, ?)",
                    (1, func_id),
                )
            for func_id in default_user_func_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO role_functions (role_id, function_id) VALUES (?, ?)",
                    (normal_role_id, func_id),
                )

        # ── 种子：系统配置默认值（v0.11 新增, v1.3.5 扩展至 19 项 #99）──
        existing_config = conn.execute("SELECT COUNT(*) as cnt FROM system_config").fetchone()
        if existing_config["cnt"] == 0:
            default_configs = [
                # === general（常规设置）===
                ("system_name", "瞭望与问数系统", "系统名称，显示在页面标题和头部导航栏", "general"),
                ("system_subtitle", "DataFinderAgentOS", "系统副标题/英文名称，显示在头部版本号旁", "general"),
                ("system_logo", "", "系统 Logo 图片路径（相对于 static 目录），为空则显示文字 Logo", "general"),
                ("icp_number", "", "ICP 备案号，显示在页面底部", "general"),
                ("default_port", "10010", "默认服务端口（重启后生效，环境变量 PORT 优先级更高）", "general"),
                # === ai（AI 默认参数）===
                ("ai_default_model", "", "AI 默认模型 ID（空=使用 is_default=1 的模型）", "ai"),
                ("ai_default_temperature", "0.7", "AI 默认温度参数（0-2）", "ai"),
                ("ai_default_max_tokens", "4096", "AI 默认最大输出 Token 数", "ai"),
                # === backup（备份策略）=== #99
                ("db_backup_path", "backups/", "数据库备份文件存放路径（相对于项目根目录）", "backup"),
                ("db_backup_interval_days", "7", "数据库自动备份间隔天数", "backup"),
                ("db_backup_keep_count", "5", "备份文件最大保留份数（超出自动清理旧文件）", "backup"),
                # === logging（日志配置）=== #99
                ("log_level", "INFO", "应用日志级别：DEBUG / INFO / WARNING / ERROR", "logging"),
                # === notification（通知配置）=== #99
                ("smtp_host", "", "SMTP 邮件服务器地址（为空则不启用邮件通知）", "notification"),
                ("webhook_url", "", "Webhook 通知 URL（为空则不启用 Webhook 通知）", "notification"),
                # === collector（采集配置）=== #99
                ("collector_interval_minutes", "60", "全局默认采集调度间隔（分钟）", "collector"),
                # === security（安全策略）=== #99
                ("captcha_enabled", "false", "是否启用登录验证码（true/false）", "security"),
                ("registration_enabled", "true", "是否允许新用户注册（true/false）", "security"),
                ("session_expire_hours", "24", "用户会话过期时间（小时）", "security"),
                # === upload（上传限制）=== #99
                ("upload_max_size_mb", "10", "文件上传大小限制（MB）", "upload"),
            ]
            conn.executemany(
                "INSERT INTO system_config (key, value, description, category) VALUES (?, ?, ?, ?)",
                default_configs,
            )
            print("[种子] 默认系统配置已创建（19 项）")

        # #99: 迁移已有数据库 — 确保新配置项存在（使用 upsert 避免重复）
        _MIGRATE_NEW_CONFIGS = [
            ("db_backup_path", "backups/", "数据库备份文件存放路径（相对于项目根目录）", "backup"),
            ("db_backup_interval_days", "7", "数据库自动备份间隔天数", "backup"),
            ("db_backup_keep_count", "5", "备份文件最大保留份数（超出自动清理旧文件）", "backup"),
            ("log_level", "INFO", "应用日志级别：DEBUG / INFO / WARNING / ERROR", "logging"),
            ("smtp_host", "", "SMTP 邮件服务器地址（为空则不启用邮件通知）", "notification"),
            ("webhook_url", "", "Webhook 通知 URL（为空则不启用 Webhook 通知）", "notification"),
            ("collector_interval_minutes", "60", "全局默认采集调度间隔（分钟）", "collector"),
            ("captcha_enabled", "false", "是否启用登录验证码（true/false）", "security"),
            ("registration_enabled", "true", "是否允许新用户注册（true/false）", "security"),
            ("session_expire_hours", "24", "用户会话过期时间（小时）", "security"),
            ("upload_max_size_mb", "10", "文件上传大小限制（MB）", "upload"),
        ]
        migrated = 0
        for key, value, desc, cat in _MIGRATE_NEW_CONFIGS:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO system_config (key, value, description, category) VALUES (?, ?, ?, ?)",
                (key, value, desc, cat),
            )
            if cursor.rowcount > 0:
                migrated += 1
        if migrated > 0:
            print(f"[迁移] 已补充 {migrated} 项新配置（#99 扩展）")

        conn.commit()

    _seed_default_sources()
    _seed_default_models()
    _seed_default_mcp_tools()
    _seed_script_tools()
    skills_created = _seed_default_skills()
    _seed_default_interfaces()
    employees_created = _seed_default_employees()

    # ── v1.2.0 舆情大屏：默认敏感词 ──
    from app.models.sensitive_word import SensitiveWordRepository
    SensitiveWordRepository.seed_default()
    _synchronize_default_capabilities(skills_created, employees_created)


def _seed_default_sources():
    """种子：默认瞭望源（百度新闻采集规则）。"""
    import json
    with get_db() as conn:
        existing = conn.execute("SELECT COUNT(*) as cnt FROM watch_sources").fetchone()
        if existing["cnt"] == 0:
            headers = {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Host": "www.baidu.com",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
            }
            conn.execute(
                "INSERT INTO watch_sources (id, name, description, url_template, request_headers, is_enabled, sort_order) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    1,
                    "百度新闻",
                    "百度新闻搜索采集源，支持关键词和分页参数",
                    "https://www.baidu.com/s?rtt=1&bsst=1&cl=2&tn=news&rsv_dl=ns_pc&word={keyword}&pn={page}",
                    json.dumps(headers, ensure_ascii=False),
                    1,
                    1,
                ),
            )
            print("[种子] 默认瞭望源已创建（百度新闻）")


def _seed_default_models():
    """种子：默认AI模型（涵盖6种分类，借鉴冯凯乐/陈子墨的丰富模型支持）。"""
    with get_db() as conn:
        existing = conn.execute("SELECT COUNT(*) as cnt FROM ai_models").fetchone()
        if existing["cnt"] == 0:
            # 文本模型 — GPT-4o-mini（非默认，保留作为备选）
            conn.execute(
                "INSERT INTO ai_models (id, name, provider, api_base, model_name, category, is_enabled, is_default) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (1, "GPT-4o-mini", "openai", "https://api.openai.com/v1", "gpt-4o-mini", "text", 1, 0),
            )
            # DeepSeek-V4（默认模型，从环境变量读取 API Key，加密存储）
            # 模型名: deepseek-v4-flash（deepseek-chat 将于 2026/07/24 弃用）
            deepseek_key = os.environ.get("DEEPSEEK_API_KEY", "")
            if deepseek_key:
                from app.utils.security import encrypt_api_key
                deepseek_key = encrypt_api_key(deepseek_key)
            else:
                print("[种子] 提示: DEEPSEEK_API_KEY 未设置，DeepSeek 模型将使用 Mock 模式")
            conn.execute(
                "INSERT INTO ai_models (id, name, provider, api_base, api_key, model_name, category, is_enabled, is_default) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (2, "DeepSeek-V4", "deepseek", "https://api.deepseek.com", deepseek_key,
                 "deepseek-v4-flash", "text", 1, 1),
            )
            # 多模态模型（新增）
            conn.execute(
                "INSERT INTO ai_models (id, name, provider, api_base, model_name, category, is_enabled, is_default) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (3, "GPT-4o", "openai", "https://api.openai.com/v1", "gpt-4o", "multimodal", 1, 0),
            )
            # 图像模型（新增）
            conn.execute(
                "INSERT INTO ai_models (id, name, provider, api_base, model_name, category, is_enabled, is_default) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (4, "DALL-E 3", "openai", "https://api.openai.com/v1", "dall-e-3", "image", 1, 0),
            )
            # 嵌入模型（新增）
            conn.execute(
                "INSERT INTO ai_models (id, name, provider, api_base, model_name, category, is_enabled, is_default) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (5, "text-embedding-3-small", "openai", "https://api.openai.com/v1",
                 "text-embedding-3-small", "embedding", 1, 0),
            )
            # 音频模型（新增）
            conn.execute(
                "INSERT INTO ai_models (id, name, provider, api_base, model_name, category, is_enabled, is_default) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (6, "Whisper-1", "openai", "https://api.openai.com/v1", "whisper-1", "audio", 1, 0),
            )
            # AIGC 媒体生成模型（Issue #21/#22 — 多模态生图/生视频）
            conn.execute(
                "INSERT INTO ai_models (id, name, provider, api_base, model_name, category, is_enabled, is_default) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (7, "Wan2.6-T2I", "custom", "https://aigc-api.aitoolcore.com/api/v1",
                 "wan2.6-t2i", "image", 1, 1),
            )
            conn.execute(
                "INSERT INTO ai_models (id, name, provider, api_base, model_name, category, is_enabled, is_default) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (8, "Qwen-Image-2.0", "custom", "https://aigc-api.aitoolcore.com/api/v1",
                 "qwen-image-2.0", "image", 1, 0),
            )
            conn.execute(
                "INSERT INTO ai_models (id, name, provider, api_base, model_name, category, is_enabled, is_default) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (9, "Wan2.6-T2V", "custom", "https://aigc-api.aitoolcore.com/api/v1",
                 "wan2.6-t2v", "video", 1, 1),
            )
            conn.execute(
                "INSERT INTO ai_models (id, name, provider, api_base, model_name, category, is_enabled, is_default) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (10, "Wan2.6-I2V", "custom", "https://aigc-api.aitoolcore.com/api/v1",
                 "wan2.6-i2v", "video", 1, 0),
            )
            print("[种子] 默认AI模型已创建（10个模型，覆盖6种分类）")


def _seed_default_interfaces():
    """种子：默认接口模板（供 API 型数字员工复用）。返回天气接口 ID。"""
    import json
    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM api_interfaces WHERE name = ?", ("天气查询接口",)
        ).fetchone()
        if existing:
            return existing["id"]

        cur = conn.execute(
            "INSERT INTO api_interfaces (name, description, api_url, api_method, "
            "api_headers, api_params_template, response_render_template, sort_order, is_enabled) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "天气查询接口",
                "wttr.in 天气查询 JSON 接口，支持将用户输入作为城市名。",
                "https://wttr.in/{message}?format=j1",
                "GET",
                json.dumps({"Accept": "application/json"}, ensure_ascii=False),
                "",
                json.dumps({
                    "type": "weather_card",
                    "title": "{{current_condition.0.weatherDesc.0.value}}",
                    "fields": [
                        {"label": "温度", "value": "{{current_condition.0.temp_C}}°C"},
                        {"label": "体感温度", "value": "{{current_condition.0.FeelsLikeC}}°C"},
                        {"label": "湿度", "value": "{{current_condition.0.humidity}}%"},
                        {"label": "风力", "value": "{{current_condition.0.windspeedKmph}} km/h"},
                        {"label": "风向", "value": "{{current_condition.0.winddir16Point}}"},
                    ]
                }, ensure_ascii=False),
                1,
                1,
            ),
        )
        weather_interface_id = cur.lastrowid
        if weather_interface_id:
            print("[种子] 默认接口模板已创建（天气查询接口）")
        return weather_interface_id


def _seed_default_employees():
    """种子：默认数字化员工（产业专员 + 天机助手 + 天气 + 采集专员 + 文案编写 + 新闻聚合 + 科普助手 + 随机音乐）。"""
    import json
    with get_db() as conn:
        # 按名称查找所有 MCP 工具 ID，避免硬编码数字 ID 导致 ID 漂移
        tool_name_to_id = {
            r["name"]: r["id"]
            for r in conn.execute("SELECT id, name FROM mcp_tools").fetchall()
        }
        resolve_tools = lambda names: [tool_name_to_id[name] for name in names if name in tool_name_to_id]
        weather_interface = conn.execute(
            "SELECT id FROM api_interfaces WHERE name = ?", ("天气查询接口",)
        ).fetchone()
        weather_interface_id = weather_interface["id"] if weather_interface else None
        existing = conn.execute("SELECT COUNT(*) as cnt FROM digital_employees").fetchone()
        created = existing["cnt"] == 0
        if created:
            # 产业专员 — LLM 型数字员工
            conn.execute(
                "INSERT INTO digital_employees (id, name, employee_type, description, "
                "model_id, system_prompt, skills, crawl4ai_enabled, mcp_tool_ids, is_enabled) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    1, "产业专员", "llm",
                    "专注于产业分析和行业研究的AI助手，能够追踪行业动态、分析产业链结构、生成产业报告",
                    None,
                    "你是一位专业的产业分析师，擅长：\n"
                    "1. 产业链结构分析与上下游关系梳理\n"
                    "2. 行业政策解读与趋势预判\n"
                    "3. 竞品分析与市场格局评估\n"
                    "4. 技术路线演进追踪\n"
                    "请用专业但不晦涩的语言回答，引用数据时注明来源。",
                    json.dumps(["产业分析", "政策解读", "竞品分析", "趋势预判"], ensure_ascii=False),
                    1,
                    json.dumps([tool_name_to_id[n] for n in [
                        "search_warehouse", "get_recent_warehouse_data", "get_warehouse_stats",
                        "search_warehouse_fulltext", "collect_web_data", "list_watch_sources",
                    ]], ensure_ascii=False),
                    1,
                ),
            )
            # 天机助手 — LLM 型数字员工
            conn.execute(
                "INSERT INTO digital_employees (id, name, employee_type, description, "
                "model_id, system_prompt, skills, crawl4ai_enabled, mcp_tool_ids, is_enabled) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    2, "天机助手", "llm",
                    "通用智能助手，具备信息检索、数据分析、文案撰写、代码辅助等多维能力",
                    None,
                    "你是天机助手，一个多才多艺的AI助手。你能够：\n"
                    "1. 快速检索和整理网络信息\n"
                    "2. 进行数据分析和可视化建议\n"
                    "3. 撰写各类文案（报告、邮件、方案等）\n"
                    "4. 提供编程和技术问题解答\n"
                    "请保持友好、高效的回答风格，根据用户需求灵活调整。",
                    json.dumps(["信息检索", "数据分析", "文案撰写", "代码辅助"], ensure_ascii=False),
                    0,
                    json.dumps([tool_name_to_id[n] for n in [
                        "search_warehouse", "get_recent_warehouse_data", "get_warehouse_stats",
                        "search_warehouse_fulltext", "collect_web_data", "list_digital_employees",
                        "list_ai_models", "list_conversations", "load_skill",
                    ]], ensure_ascii=False),
                    1,
                ),
            )
            # ── v1.7.0: 创建天气 MCP API 型工具，替代旧 HTTP 直连 ──
            weather_tool_id = conn.execute(
                "SELECT id FROM mcp_tools WHERE name = ?", ("weather_query",)
            ).fetchone()
            if not weather_tool_id:
                cur = conn.execute(
                    "INSERT INTO mcp_tools (name, display_name, description, category, tool_type, "
                    "api_url, api_method, api_headers, input_schema, is_enabled, is_system, sort_order) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "weather_query", "天气查询",
                        "通过 wttr.in 免费 API 查询指定城市的实时天气信息，返回温度、天气状况、湿度、风力等数据。",
                        "general", "api",
                        "https://wttr.in/{message}?format=j1",
                        "GET",
                        json.dumps({"Accept": "application/json"}, ensure_ascii=False),
                        json.dumps({
                            "type": "object",
                            "properties": {
                                "message": {"type": "string", "description": "城市名称，如 Beijing、成都、London"}
                            },
                            "required": ["message"]
                        }, ensure_ascii=False),
                        1, 0, 99,
                    ),
                )
                weather_tool_id = cur.lastrowid
                print("[种子] 天气 MCP API 工具已创建（weather_query）")
            else:
                weather_tool_id = weather_tool_id["id"]

            # 天气查询 — API 型数字员工（v1.7.0: 绑定 MCP 工具替代旧 HTTP 直连）
            conn.execute(
                "INSERT INTO digital_employees (id, name, employee_type, description, "
                "api_url, api_method, api_headers, api_params_template, response_render_template, "
                "api_interface_id, mcp_tool_id, is_enabled) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    3, "天气", "api",
                    "查询指定城市的天气信息，返回温度、天气状况、风力等",
                    "https://wttr.in/{message}?format=j1",  # 保留用于旧架构兼容
                    "GET",
                    json.dumps({"Accept": "application/json"}, ensure_ascii=False),
                    "",
                    json.dumps({
                        "type": "weather_card",
                        "title": "{{current_condition.0.weatherDesc.0.value}}",
                        "fields": [
                            {"label": "温度", "value": "{{current_condition.0.temp_C}}°C"},
                            {"label": "体感温度", "value": "{{current_condition.0.FeelsLikeC}}°C"},
                            {"label": "湿度", "value": "{{current_condition.0.humidity}}%"},
                            {"label": "风力", "value": "{{current_condition.0.windspeedKmph}} km/h"},
                            {"label": "风向", "value": "{{current_condition.0.winddir16Point}}"},
                        ]
                    }, ensure_ascii=False),
                    weather_interface_id,
                    weather_tool_id,  # v1.7.0: 绑定 MCP 工具
                    1,
                ),
            )
            # 采集专员 — LLM 型数字员工（通过 MCP 工具权限使用 Crawl4ai 深度采集）
            conn.execute(
                "INSERT INTO digital_employees (id, name, employee_type, description, "
                "model_id, system_prompt, skills, crawl4ai_enabled, mcp_tool_ids, is_enabled) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    4, "采集专员", "llm",
                    "专注于数据采集与信息提取的AI助手，支持关键词搜索、深度采集、数据整理",
                    None,
                    "你是采集专员，专门负责数据采集和整理工作。你的核心能力：\n"
                    "1. 根据关键词在数据仓库中搜索相关信息\n"
                    "2. 对指定URL进行深度内容采集和正文提取\n"
                    "3. 对采集结果进行分类、归纳和摘要\n"
                    "4. 生成结构化的数据报告\n"
                    "请高效、准确地完成采集任务，输出清晰的结构化结果。",
                    json.dumps(["数据搜索", "深度采集", "内容提取", "数据整理"], ensure_ascii=False),
                    0,  # v0.8: crawl4ai_enabled 已废弃，改用 mcp_tool_ids
                    json.dumps(resolve_tools([
                        "search_warehouse", "get_recent_warehouse_data", "search_warehouse_fulltext",
                        "collect_web_data", "deep_collect_url", "list_watch_sources",
                        "collect_with_crawl4ai", "batch_deep_collect",
                    ]), ensure_ascii=False),
                    1,
                ),
            )
            # 文案编写 — LLM 型数字员工
            conn.execute(
                "INSERT INTO digital_employees (id, name, employee_type, description, "
                "model_id, system_prompt, skills, crawl4ai_enabled, mcp_tool_ids, is_enabled) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    5, "文案编写", "llm",
                    "专注于各类文案创作的AI助手，支持报告、方案、邮件、宣传稿等多种文体",
                    None,
                    "你是一位专业的文案撰写专家，擅长：\n"
                    "1. 商业报告和行业分析报告的撰写\n"
                    "2. 项目方案和策划书的编写\n"
                    "3. 正式邮件和公文的起草\n"
                    "4. 宣传稿、新闻稿的撰写\n"
                    "5. 演讲稿和PPT大纲的制作\n"
                    "请根据用户需求，输出格式规范、逻辑清晰、语言得体的专业文案。",
                    json.dumps(["报告撰写", "方案策划", "公文起草", "宣传文案", "演讲稿"], ensure_ascii=False),
                    0,
                    json.dumps([tool_name_to_id[n] for n in [
                        "search_warehouse", "get_recent_warehouse_data",
                        "list_conversations", "load_skill",
                    ]], ensure_ascii=False),
                    1,
                ),
            )
            # 新闻聚合 — LLM 型数字员工
            conn.execute(
                "INSERT INTO digital_employees (id, name, employee_type, description, "
                "model_id, system_prompt, skills, crawl4ai_enabled, mcp_tool_ids, is_enabled) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    6, "新闻聚合", "llm",
                    "专注于新闻资讯聚合与摘要的AI助手，能够快速整理热点新闻并生成简报",
                    None,
                    "你是新闻聚合助手，专门负责新闻资讯的检索与整理。你的核心能力：\n"
                    "1. 从数据仓库中检索最新新闻和资讯\n"
                    "2. 按主题/关键词整理新闻列表\n"
                    "3. 生成新闻摘要和每日简报\n"
                    "4. 追踪特定话题的新闻动态\n"
                    "请输出清晰、有条理的新闻摘要，标注来源和时间。",
                    json.dumps(["新闻检索", "资讯聚合", "热点追踪", "每日简报"], ensure_ascii=False),
                    0,
                    json.dumps([tool_name_to_id[n] for n in [
                        "search_warehouse", "get_recent_warehouse_data", "get_warehouse_stats",
                        "search_warehouse_fulltext", "collect_web_data", "list_conversations",
                    ]], ensure_ascii=False),
                    1,
                ),
            )
            # 科普助手 — LLM 型数字员工
            conn.execute(
                "INSERT INTO digital_employees (id, name, employee_type, description, "
                "model_id, system_prompt, skills, crawl4ai_enabled, mcp_tool_ids, is_enabled) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    7, "科普助手", "llm",
                    "专注于知识科普与百科问答的AI助手，能够深入浅出地解释各类知识",
                    None,
                    "你是一位知识渊博的科普专家，擅长：\n"
                    "1. 用通俗易懂的语言解释复杂概念\n"
                    "2. 解答科学、历史、文化等各类百科问题\n"
                    "3. 提供知识背景和延伸阅读建议\n"
                    "4. 从数据仓库中引用相关数据和事实\n"
                    "请用生动有趣但严谨准确的方式回答问题，必要时引用权威来源。",
                    json.dumps(["百科问答", "知识科普", "概念解释", "学术参考"], ensure_ascii=False),
                    0,
                    json.dumps([tool_name_to_id[n] for n in [
                        "search_warehouse", "get_recent_warehouse_data",
                        "search_warehouse_fulltext", "load_skill",
                    ]], ensure_ascii=False),
                    1,
                ),
            )
            # 随机音乐 — API 型数字员工（MCP 工具驱动，调用 get_random_music）
            music_tool_id = tool_name_to_id.get("get_random_music")
            conn.execute(
                "INSERT INTO digital_employees (id, name, employee_type, description, "
                "api_url, api_method, api_headers, api_params_template, response_render_template, "
                "api_interface_id, mcp_tool_id, is_enabled) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    8, "随机音乐", "api",
                    "随机推荐一首来自网易云音乐热歌榜的歌曲，展示歌曲名、歌手、封面图和试听链接",
                    "",  # api_url — 由 MCP 工具 get_random_music 内部处理，无需外部 URL
                    "GET",
                    json.dumps({"Accept": "application/json"}, ensure_ascii=False),
                    "",  # api_params_template — 工具无需额外参数
                    "",  # response_render_template — 由 _build_employee_card 自动识别音乐数据构建卡片
                    None,  # api_interface_id
                    music_tool_id,  # 绑定 MCP 工具 get_random_music
                    1,
                ),
            )
            print("[种子] 默认数字化员工已创建（8个：产业专员/天机助手/天气/采集专员/文案编写/新闻聚合/科普助手/随机音乐）")

        elif weather_interface_id:
            conn.execute(
                "UPDATE digital_employees SET api_interface_id = ? "
                "WHERE name = ? AND employee_type = 'api' "
                "AND (api_interface_id IS NULL OR api_interface_id = '')",
                (weather_interface_id, "天气"),
            )
        return created

def _seed_default_skills():
    """种子：默认技能（14个，纯 Prompt 模板，含 MCP 工具绑定）。"""
    import json
    with get_db() as conn:
        existing = conn.execute("SELECT COUNT(*) as cnt FROM skills").fetchone()
        created = existing["cnt"] == 0
        if created:
            # 按名称查找 MCP 工具 ID
            tool_name_to_id = {
                r["name"]: r["id"]
                for r in conn.execute("SELECT id, name FROM mcp_tools").fetchall()
            }
            skills_data = [
                # ── 原有 5 个技能 ──
                # 数据统计报告
                (1, "数据统计", "生成数据仓库统计报告，含图表标记",
                 "你正在进行数据统计分析任务。请遵循以下指令：\n"
                 "1. 首先调用 get_warehouse_stats 工具获取数据仓库概况\n"
                 "2. 根据统计结果生成自然语言报告，包含：总记录数、已深度采集数、来源分布\n"
                 "3. 如果数据适合可视化，请使用 [CHART:bar|pie|line] 标记建议图表类型\n"
                 "4. 报告格式清晰，使用 Markdown 标题和列表\n"
                 "5. 最后给出数据利用建议（如：可对Top来源进行深度采集）",
                 tool_name_to_id.get("get_warehouse_stats")),
                # 数据搜索
                (2, "数据搜索", "在数据仓库中按关键词搜索采集结果",
                 "你正在执行数据搜索任务。请遵循以下指令：\n"
                 "1. 使用 search_warehouse 工具搜索数据仓库，参数 keyword 填写用户搜索的关键词，limit 默认 10\n"
                 "2. 将搜索结果整理为清晰的列表格式\n"
                 "3. 每条结果输出：标题、来源、50字摘要\n"
                 "4. 如果结果较多，按相关性排序，优先展示最匹配的内容",
                 tool_name_to_id.get("search_warehouse")),
                # 新闻摘要
                (3, "新闻摘要", "聚合多源新闻并生成结构化摘要",
                 "你正在执行新闻摘要任务。请遵循以下指令：\n"
                 "1. 调用 search_warehouse 或 get_recent_warehouse_data 获取新闻数据\n"
                 "2. 按主题分类整理新闻（如：科技/财经/政策/社会）\n"
                 "3. 每条新闻输出：标题、来源、50字摘要、发布时间\n"
                 "4. 在末尾生成一份「今日要闻速览」（3-5条最重要新闻）\n"
                 "5. 使用 Markdown 格式，标题用 ###，列表用 -",
                 tool_name_to_id.get("get_recent_warehouse_data")),
                # 深度采集
                (4, "深度采集", "对指定 URL 进行正文深度抓取和内容提取",
                 "你正在执行深度采集任务。请遵循以下指令：\n"
                 "1. 使用 deep_collect_url 工具对用户提供的 URL 进行深度采集\n"
                 "2. 如果 URL 内容复杂，可额外使用 collect_with_crawl4ai 工具获取更完整内容\n"
                 "3. 提取文章正文、标题、关键信息\n"
                 "4. 输出结构化内容：标题 → 正文摘要 → 关键数据 → 来源链接\n"
                 "5. 用 Markdown 格式组织输出",
                 tool_name_to_id.get("deep_collect_url")),
                # 翻译助手（纯 prompt 无需 MCP 工具）
                (5, "翻译助手", "高质量中英文双向翻译，保持专业术语准确",
                 "你正在执行翻译任务。请遵循以下指令：\n"
                 "1. 识别用户输入的源语言和目标语言\n"
                 "2. 执行高质量翻译，注意：\n"
                 "   - 保持原文语义和语气\n"
                 "   - 专业术语使用行业标准译法\n"
                 "   - 长句合理断句，符合目标语言习惯\n"
                 "3. 输出格式：先给出翻译结果，再附加【术语注释】（如有专业术语）\n"
                 "4. 如涉及中文成语/典故，添加简短解释",
                 None),

                # ── 新增 9 个技能（来自 TAG_SKILL_MAP）──
                (6, "产业分析", "分析产业链结构、上下游关系和行业格局",
                 "你正在执行产业分析任务。请遵循以下指令：\n"
                 "1. 使用 search_warehouse 或 get_recent_warehouse_data 获取相关产业数据\n"
                 "2. 分析产业链结构：上游供应商、中游制造商、下游渠道和终端用户\n"
                 "3. 识别关键节点和瓶颈环节\n"
                 "4. 评估产业集中度和竞争格局\n"
                 "5. 使用 get_warehouse_stats 了解数据概况作为参考\n"
                 "6. 输出结构化的产业分析报告，使用 Markdown 格式",
                 tool_name_to_id.get("search_warehouse")),  # 主要工具，实际可调用多个
                (7, "政策解读", "解读行业政策法规，分析政策影响",
                 "你正在执行政策解读任务。请遵循以下指令：\n"
                 "1. 使用 search_warehouse 或 collect_web_data 搜集相关政策文本和解读\n"
                 "2. 提取政策核心要点和关键条款\n"
                 "3. 分析政策对不同利益相关方的影响\n"
                 "4. 预测政策实施后的行业变化趋势\n"
                 "5. 使用 get_recent_warehouse_data 获取最新的政策动态\n"
                 "6. 输出清晰的政策解读报告",
                 tool_name_to_id.get("search_warehouse")),
                (8, "竞品分析", "对比分析竞争对手的产品、策略和市场表现",
                 "你正在执行竞品分析任务。请遵循以下指令：\n"
                 "1. 使用 search_warehouse 搜索竞品相关信息\n"
                 "2. 从产品功能、定价策略、市场份额、用户评价等维度对比\n"
                 "3. 使用 get_recent_warehouse_data 获取最新动态\n"
                 "4. 使用 get_warehouse_stats 了解整体数据分布\n"
                 "5. 输出 SWOT 分析或对比矩阵\n"
                 "6. 使用 Markdown 表格呈现对比数据",
                 tool_name_to_id.get("search_warehouse")),
                (9, "趋势预判", "基于数据趋势分析，预判行业和技术发展方向",
                 "你正在执行趋势预判任务。请遵循以下指令：\n"
                 "1. 使用 get_recent_warehouse_data 获取最新数据\n"
                 "2. 使用 get_warehouse_stats 分析整体数据趋势\n"
                 "3. 使用 search_warehouse 搜索历史相关数据\n"
                 "4. 识别关键变化趋势和拐点\n"
                 "5. 预测未来3-6个月的发展方向\n"
                 "6. 输出趋势分析报告，包含数据支撑和预测依据",
                 tool_name_to_id.get("get_warehouse_stats")),
                (10, "文案撰写", "撰写各类商业文案、报告、方案等专业文档",
                 "你正在执行文案撰写任务。请遵循以下指令：\n"
                 "1. 使用 search_warehouse 和 get_recent_warehouse_data 搜集背景资料\n"
                 "2. 使用 load_skill 加载相关技能模板（如需要）\n"
                 "3. 根据用户需求选择文体格式\n"
                 "4. 保持逻辑清晰、语言专业、格式规范\n"
                 "5. 必要时添加数据引用和来源标注\n"
                 "6. 输出可直接使用的最终文稿",
                 tool_name_to_id.get("load_skill")),
                (11, "代码辅助", "提供编程问题解答、代码审查和技术方案建议",
                 "你正在执行代码辅助任务。请遵循以下指令：\n"
                 "1. 理解用户的技术问题和编程需求\n"
                 "2. 提供清晰、可运行的代码示例\n"
                 "3. 解释关键算法和设计思路\n"
                 "4. 标注潜在的性能问题或安全隐患\n"
                 "5. 必要时提供替代方案和最佳实践\n"
                 "6. 使用代码块格式输出代码，注明语言类型",
                 None),  # 代码辅助主要靠 LLM 自身能力
                (12, "百科问答", "解答各类知识性问题，提供准确的百科信息",
                 "你正在执行百科问答任务。请遵循以下指令：\n"
                 "1. 使用 search_warehouse 或 search_warehouse_fulltext 检索相关知识\n"
                 "2. 使用 get_recent_warehouse_data 获取最新资讯补充\n"
                 "3. 提供准确、客观的百科知识解答\n"
                 "4. 区分事实和观点，标注不确定信息\n"
                 "5. 引用权威来源，提供延伸阅读建议\n"
                 "6. 用通俗易懂的语言解释专业概念",
                 tool_name_to_id.get("search_warehouse")),
                (13, "信息检索", "高效检索和整理多源信息，生成结构化摘要",
                 "你正在执行信息检索任务。请遵循以下指令：\n"
                 "1. 使用 search_warehouse 或 search_warehouse_fulltext 进行关键词检索\n"
                 "2. 使用 get_recent_warehouse_data 补充最新信息\n"
                 "3. 对检索结果去重、分类和排序\n"
                 "4. 生成结构化信息摘要\n"
                 "5. 标注每条信息的来源和时间\n"
                 "6. 使用 Markdown 列表和表格组织输出",
                 tool_name_to_id.get("search_warehouse")),
                (14, "数据分析", "对采集数据进行分析处理，生成数据洞察",
                 "你正在执行数据分析任务。请遵循以下指令：\n"
                 "1. 使用 get_warehouse_stats 了解数据全貌\n"
                 "2. 使用 get_recent_warehouse_data 获取待分析数据\n"
                 "3. 使用 search_warehouse 检索特定维度数据\n"
                 "4. 进行数据清洗、统计和趋势分析\n"
                 "5. 识别异常值和数据模式\n"
                 "6. 生成数据分析报告，包含图表建议",
                 tool_name_to_id.get("get_warehouse_stats")),
            ]
            conn.executemany(
                "INSERT INTO skills (id, name, description, prompt_template, mcp_tool_id) "
                "VALUES (?, ?, ?, ?, ?)",
                skills_data,
            )
            print("[种子] 默认技能已创建（14个：数据统计/数据搜索/新闻摘要/深度采集/翻译助手/产业分析/政策解读/竞品分析/趋势预判/文案撰写/代码辅助/百科问答/信息检索/数据分析）")
        return created


def _seed_default_mcp_tools():
    """种子：MCP 工具注册表（20+ 工具）。"""
    import json
    with get_db() as conn:
        from app.mcp.catalog import upsert_builtin_tools
        inserted = upsert_builtin_tools(conn)
        conn.commit()
        print(f"[种子] MCP 工具目录已同步（{inserted}个内置工具）")
        return

        tools_data = [
            # ── 数据仓库类 (warehouse) ──
            (1, "search_warehouse", "数据仓库搜索", "在瞭望与问数系统的数据仓库中搜索关键词相关的内容。当用户询问「有没有关于XX的数据」「搜索XX」「查找XX」「帮我找XX」等问题时使用此工具。不要用于获取最新数据或统计信息（请使用其他专用工具）。", "warehouse", "builtin",
             "app.mcp.builtin_tools.warehouse_tools._search_warehouse", "", "GET", "{}", "",
             json.dumps({"type":"object","properties":{"keyword":{"type":"string","description":"搜索关键词"},"limit":{"type":"integer","description":"返回结果数量上限，默认10","default":10}},"required":["keyword"]}, ensure_ascii=False),
             "{}", 1, 1, 1, "{}"),
            (2, "get_recent_warehouse_data", "最新数据查询", "获取数据仓库中最新入库的数据记录。当用户询问「最新数据」「最近有什么」「看看数据仓库」「浏览数据」时使用此工具。也适用于用户没有明确关键词但想了解数据仓库内容时。", "warehouse", "builtin",
             "app.mcp.builtin_tools.warehouse_tools._get_recent_warehouse_data", "", "GET", "{}", "",
             json.dumps({"type":"object","properties":{"limit":{"type":"integer","description":"返回记录数，默认10","default":10}}}, ensure_ascii=False),
             "{}", 1, 1, 2, "{}"),
            (3, "get_warehouse_stats", "数据统计", "获取数据仓库的统计概况，包括总记录数、已深度采集数、来源分布等。当用户询问「有多少数据」「数据统计」「数据概况」「数据分布」时使用此工具。", "warehouse", "builtin",
             "app.mcp.builtin_tools.warehouse_tools._get_warehouse_stats", "", "GET", "{}", "",
             json.dumps({"type":"object","properties":{}}, ensure_ascii=False),
             "{}", 1, 1, 3, "{}"),
            (4, "search_warehouse_fulltext", "全文检索(FTS5)", "使用 FTS5 全文搜索引擎在数据仓库中进行高级全文检索。比普通关键词搜索更精确，支持布尔表达式和短语匹配。当用户需要精确查找某段文字或使用高级搜索语法时使用此工具。", "warehouse", "builtin",
             "app.mcp.builtin_tools.warehouse_tools._search_warehouse_fulltext", "", "GET", "{}", "",
             json.dumps({"type":"object","properties":{"query":{"type":"string","description":"全文检索关键词"},"limit":{"type":"integer","description":"返回数量","default":10}},"required":["query"]}, ensure_ascii=False),
             "{}", 1, 1, 4, "{}"),

            # ── 数据采集类 (collect) ──
            (5, "collect_web_data", "全网采集", "执行全网瞭望数据采集任务，从配置的瞭望源（如百度新闻、搜狗新闻等）搜索指定关键词。当用户要求「采集关于XX的新闻」「帮我在网上搜索XX」「瞭望一下XX」时使用此工具。注意：这是一个批量采集工具，不是搜索数据仓库已有内容。", "collect", "builtin",
             "app.mcp.builtin_tools.collect_tools._collect_web_data", "", "GET", "{}", "",
             json.dumps({"type":"object","properties":{"keyword":{"type":"string","description":"采集关键词"},"source_ids":{"type":"array","items":{"type":"integer"},"description":"瞭望源ID列表"}},"required":["keyword"]}, ensure_ascii=False),
             "{}", 1, 1, 1, "{}"),
            (6, "deep_collect_url", "深度采集URL", "对指定网页 URL 进行深度内容采集，提取文章正文、标题等结构化内容。当用户提供具体URL并要求「深度采集」「抓取这个网页」「提取文章内容」「帮我看看这个链接」时使用。仅用于采集单个 URL 的详细内容，不是搜索引擎。", "collect", "builtin",
             "app.mcp.builtin_tools.collect_tools._deep_collect_url", "", "GET", "{}", "",
             json.dumps({"type":"object","properties":{"url":{"type":"string","description":"目标网页URL"}},"required":["url"]}, ensure_ascii=False),
             "{}", 1, 1, 2, "{}"),
            (7, "list_watch_sources", "瞭望源列表", "列出系统中所有已启用的瞭望源（数据采集源）。当用户询问「有哪些采集源」「瞭望源列表」「从哪些网站采集数据」时使用此工具。", "collect", "builtin",
             "app.mcp.builtin_tools.collect_tools._list_watch_sources", "", "GET", "{}", "",
             json.dumps({"type":"object","properties":{}}, ensure_ascii=False),
             "{}", 1, 1, 3, "{}"),

            # ── 数字员工类 (employee) ──
            (8, "list_digital_employees", "数字员工列表", "列出系统中所有可用的数字员工。当用户询问「有哪些数字员工」「可以用哪些助手」「@谁」或不确定该调用哪个员工时使用。", "employee", "builtin",
             "app.mcp.builtin_tools.employee_tools._list_digital_employees", "", "GET", "{}", "",
             json.dumps({"type":"object","properties":{}}, ensure_ascii=False),
             "{}", 1, 1, 1, "{}"),
            (9, "invoke_digital_employee", "调用数字员工", "调用指定的数字员工执行任务。支持按名称或 ID 查找员工，将用户消息转发给该员工并返回执行结果。当用户想委托特定员工完成某项工作时使用此工具。", "employee", "builtin",
             "app.mcp.builtin_tools.employee_tools._invoke_digital_employee", "", "GET", "{}", "",
             json.dumps({"type":"object","properties":{"employee_name":{"type":"string","description":"员工名称或ID"},"message":{"type":"string","description":"发送给员工的消息"}},"required":["employee_name","message"]}, ensure_ascii=False),
             "{}", 1, 1, 2, "{}"),

            # ── AI模型类 (model) ──
            (10, "list_ai_models", "AI模型列表", "列出系统中所有已启用的 AI 模型，包括模型名称、提供商、分类和默认状态。当用户询问「有哪些AI模型」「当前可用模型」「切换模型」时使用此工具。", "model", "builtin",
             "app.mcp.builtin_tools.model_tools._list_ai_models", "", "GET", "{}", "",
             json.dumps({"type":"object","properties":{}}, ensure_ascii=False),
             "{}", 1, 1, 1, "{}"),
            (11, "get_default_model", "获取默认模型", "获取当前系统默认的 AI 模型信息。当用户询问「当前用的是什么模型」「默认模型是什么」时使用此工具。", "model", "builtin",
             "app.mcp.builtin_tools.model_tools._get_default_model", "", "GET", "{}", "",
             json.dumps({"type":"object","properties":{}}, ensure_ascii=False),
             "{}", 1, 1, 2, "{}"),

            # ── 对话管理类 (chat) ──
            (12, "list_conversations", "对话历史", "列出用户的历史对话记录。当用户询问「之前的对话」「对话历史」「我之前的提问」时使用此工具。", "chat", "builtin",
             "app.mcp.builtin_tools.chat_tools._list_conversations", "", "GET", "{}", "",
             json.dumps({"type":"object","properties":{"username":{"type":"string","description":"用户名"},"limit":{"type":"integer","description":"返回数量上限","default":20}}}, ensure_ascii=False),
             "{}", 1, 1, 1, "{}"),
            (13, "get_conversation_messages", "对话消息", "获取指定对话的完整消息历史。当用户指定对话ID要求「查看那个对话」「回顾之前的聊天」时使用。", "chat", "builtin",
             "app.mcp.builtin_tools.chat_tools._get_conversation_messages", "", "GET", "{}", "",
             json.dumps({"type":"object","properties":{"conversation_id":{"type":"integer","description":"对话ID"},"limit":{"type":"integer","description":"消息数量上限","default":20},"username":{"type":"string","description":"当前用户名"}},"required":["conversation_id"]}, ensure_ascii=False),
             "{}", 1, 1, 2, "{}"),

            # ── 娱乐类 (entertainment) ──
            (14, "get_random_music", "随机音乐", "随机推荐一首歌曲。从网易云音乐热歌榜中随机选取一首，返回歌曲名、歌手、封面图和试听链接。当用户说「来首歌」「随机音乐」「推荐一首歌」「放首歌」「来点音乐」时使用此工具。注意：此工具直接返回歌曲数据，调用后应基于数据向用户展示歌曲信息。", "entertainment", "builtin",
             "app.mcp.builtin_tools.entertainment_tools._get_random_music", "", "GET", "{}", "",
             json.dumps({"type":"object","properties":{}}, ensure_ascii=False),
             "{}", 1, 1, 1, "{}"),

            # ── 爬虫增强类 (crawl4ai) ──
            (15, "collect_with_crawl4ai", "Crawl4ai智能采集", "使用 Crawl4ai 智能爬虫引擎对指定 URL 进行深度网页内容采集。替代旧的 crawl4ai_enabled 复选框功能，支持自动检测页面结构并提取正文。优先使用 crawl4ai 引擎，不可用时回退到标准采集。当用户提供 URL 并要求「用 crawl4ai 采集」「智能爬取这个网页」时使用。", "crawl4ai", "builtin",
             "app.mcp.builtin_tools.crawl4ai_tools._collect_with_crawl4ai", "", "GET", "{}", "",
             json.dumps({"type":"object","properties":{"url":{"type":"string","description":"目标URL"},"extract_mode":{"type":"string","enum":["auto","article","full"],"default":"auto"}},"required":["url"]}, ensure_ascii=False),
             "{}", 1, 1, 1, "{}"),
            (16, "batch_deep_collect", "批量深度采集", "批量对多个 URL 进行深度内容采集。一次性提交多个链接，系统逐一采集并汇总结果。当用户需要「批量抓取这些网页」「同时采集这几个链接」时使用此工具。", "crawl4ai", "builtin",
             "app.mcp.builtin_tools.crawl4ai_tools._batch_deep_collect", "", "GET", "{}", "",
             json.dumps({"type":"object","properties":{"urls":{"type":"array","items":{"type":"string"},"description":"目标URL列表"},"extract_mode":{"type":"string","enum":["auto","article","full"],"default":"auto"}},"required":["urls"]}, ensure_ascii=False),
             "{}", 1, 1, 2, "{}"),

            # ── 系统管理类 (system) ──
            (17, "load_skill", "加载技能", "加载指定技能的完整执行指令。当系统提示中的「可用技能」列表里存在你需要的技能时，调用此工具获取该技能的详细 prompt 模板或 function 映射。不要猜测技能内容，始终通过此工具按需加载。", "system", "builtin",
             "app.mcp.builtin_tools.system_tools._load_skill", "", "GET", "{}", "",
             json.dumps({"type":"object","properties":{"skill_name":{"type":"string","description":"技能名称"}},"required":["skill_name"]}, ensure_ascii=False),
             "{}", 1, 1, 1, "{}"),
            (18, "get_system_stats", "系统统计", "获取系统整体统计概览，包括用户数、数据仓库记录数、数字员工数、AI模型数、瞭望源数和对话数。当用户询问「系统概况」「系统有多少数据」「整体统计」时使用此工具。", "system", "builtin",
             "app.mcp.builtin_tools.system_tools._get_system_stats", "", "GET", "{}", "",
             json.dumps({"type":"object","properties":{}}, ensure_ascii=False),
             "{}", 1, 1, 2, "{}"),
        ]

        conn.executemany(
            "INSERT INTO mcp_tools (id, name, display_name, description, category, tool_type, "
            "handler_module, api_url, api_method, api_headers, api_params_template, "
            "input_schema, output_schema, is_enabled, is_system, sort_order, config) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            tools_data,
        )
        print("[种子] 默认 MCP 工具已创建（18个工具，覆盖7个分类）")


def _seed_script_tools():
    """v2.0 种子: script 型 MCP 工具。按名称动态查询 api_interfaces 获取 interface_id。"""
    import json
    with get_db() as conn:
        # 按名称查询接口ID，不硬编码
        weather_iface = conn.execute(
            "SELECT id FROM api_interfaces WHERE name='天气查询接口' AND interface_type='external'"
        ).fetchone()
        music_iface = conn.execute(
            "SELECT id FROM api_interfaces WHERE name='网易云音乐热歌榜' AND interface_type='external'"
        ).fetchone()

        if not weather_iface or not music_iface:
            logger.warning("[种子] 外部接口未就绪，跳过 script 工具种子")
            return

        weather_id = weather_iface["id"]
        music_id = music_iface["id"]

        tools = [
            # ── 天气 script 型工具 ──
            {
                "name": "weather_script",
                "display_name": "天气查询 (脚本)",
                "description": "通过 wttr.in 免费 API 查询指定城市的实时天气信息。脚本型工具。",
                "category": "data_warehouse",
                "tool_type": "script",
                "input_schema": json.dumps({
                    "type": "object",
                    "properties": {
                        "city": {"type": "string", "description": "城市名称，如 Beijing、成都、London"}
                    },
                    "required": ["city"]
                }, ensure_ascii=False),
                "data_sources": json.dumps([{
                    "interface_id": weather_id,
                    "param_mapping": {"city": "message"}
                }], ensure_ascii=False),
                "transform_script": (
                    "def transform(data_sources):\n"
                    "    import json\n"
                    "    try:\n"
                    "        w = data_sources[0]['data']\n"
                    "        cur = w.get('current_condition', [{}])[0]\n"
                    "        loc = w.get('nearest_area', [{}])[0]\n"
                    "        city = loc.get('areaName', [{}])[0].get('value', '未知')\n"
                    "        country = loc.get('country', [{}])[0].get('value', '')\n"
                    "        temp = cur.get('temp_C', '?')\n"
                    "        desc = cur.get('weatherDesc', [{}])[0].get('value', '未知')\n"
                    "        humidity = cur.get('humidity', '?')\n"
                    "        wind = cur.get('winddir16Point', '?') + ' ' + cur.get('windspeedKmph', '?') + 'km/h'\n"
                    "        return f'{city}, {country} 当前天气: {desc}, 温度 {temp}°C, 湿度 {humidity}%, 风向风速 {wind}'\n"
                    "    except Exception as e:\n"
                    "        return f'天气数据解析失败: {e}, 原始数据: {json.dumps(data_sources)[:500]}'"
                ),
                "script_enabled": 1,
                "is_enabled": 1,
                "sort_order": 98,
            },
            # ── 音乐 script 型工具 ──
            {
                "name": "music_script",
                "display_name": "随机音乐推荐 (脚本)",
                "description": "从网易云音乐热歌榜随机推荐一首歌曲。脚本型工具。",
                "category": "entertainment",
                "tool_type": "script",
                "input_schema": json.dumps({
                    "type": "object",
                    "properties": {},
                    "required": []
                }, ensure_ascii=False),
                "data_sources": json.dumps([{
                    "interface_id": music_id,
                    "param_mapping": {}
                }], ensure_ascii=False),
                "transform_script": (
                    "def transform(data_sources):\n"
                    "    import json, random\n"
                    "    try:\n"
                    "        songs = data_sources[0].get('data', [])\n"
                    "        if isinstance(songs, list) and len(songs) > 0:\n"
                    "            song = random.choice(songs)\n"
                    "            return f'🎵 {song.get(\"name\",\"?\")} — {song.get(\"artist\",\"?\")}'\n"
                    "        return '未找到歌曲'\n"
                    "    except Exception as e:\n"
                    "        return f'音乐数据解析失败: {e}'"
                ),
                "script_enabled": 1,
                "is_enabled": 1,
                "sort_order": 99,
            },
        ]

        inserted = 0
        for t in tools:
            cur = conn.execute(
                "INSERT OR IGNORE INTO mcp_tools "
                "(name, display_name, description, category, tool_type, "
                "input_schema, data_sources, transform_script, "
                "script_enabled, is_enabled, sort_order) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (t["name"], t["display_name"], t["description"], t["category"],
                 t["tool_type"], t["input_schema"], t["data_sources"],
                 t["transform_script"], t["script_enabled"],
                 t["is_enabled"], t["sort_order"]),
            )
            if cur.rowcount > 0:
                inserted += 1
        conn.commit()
        if inserted > 0:
            print(f"[种子] script 型 MCP 工具已创建（{inserted}个工具：weather_script + music_script）")
        else:
            print("[种子] script 型 MCP 工具已存在，跳过")


def _synchronize_default_capabilities(skills_created: bool, employees_created: bool):
    """Resolve default Skill and employee tool grants by stable names."""
    import json

    skill_specs = {
        "数据统计": "get_warehouse_stats",
        "数据搜索": "search_warehouse",
        "新闻摘要": "get_recent_warehouse_data",
        "深度采集": "deep_collect_url",
        "翻译助手": None,
        "产业分析": "search_warehouse_fulltext",
        "政策解读": "search_warehouse",
        "竞品分析": "search_warehouse",
        "趋势预判": "get_warehouse_stats",
        "文案撰写": "load_skill",
        "代码辅助": "load_skill",
        "百科问答": "search_warehouse",
        "随机音乐": "get_random_music",
    }
    tag_to_skill = {
        "信息检索": "数据搜索", "数据分析": "数据统计",
        "内容提取": "深度采集", "数据整理": "数据统计",
        "报告撰写": "文案撰写", "方案策划": "文案撰写",
        "公文起草": "文案撰写", "宣传文案": "文案撰写",
        "演讲稿": "文案撰写", "新闻检索": "新闻摘要",
        "资讯聚合": "新闻摘要", "热点追踪": "新闻摘要",
        "每日简报": "新闻摘要", "知识科普": "百科问答",
        "概念解释": "百科问答", "学术参考": "百科问答",
        "歌曲推荐": "随机音乐", "音乐点播": "随机音乐",
    }
    employee_tools = {
        "产业专员": ["search_warehouse", "get_recent_warehouse_data", "get_warehouse_stats",
                     "search_warehouse_fulltext", "collect_web_data", "list_watch_sources"],
        "天机助手": ["search_warehouse", "get_recent_warehouse_data", "get_warehouse_stats",
                    "search_warehouse_fulltext", "collect_web_data", "list_digital_employees",
                    "list_ai_models", "list_conversations", "load_skill"],
        "采集专员": ["search_warehouse", "get_recent_warehouse_data", "search_warehouse_fulltext",
                    "collect_web_data", "deep_collect_url", "list_watch_sources",
                    "collect_with_crawl4ai", "batch_deep_collect"],
        "文案编写": ["search_warehouse", "get_recent_warehouse_data", "list_conversations", "load_skill"],
        "新闻聚合": ["search_warehouse", "get_recent_warehouse_data", "get_warehouse_stats",
                    "search_warehouse_fulltext", "collect_web_data", "list_conversations"],
        "科普助手": ["search_warehouse", "get_recent_warehouse_data", "search_warehouse_fulltext", "load_skill"],
        "随机音乐": ["get_random_music"],
    }

    with get_db() as conn:
        tool_rows = conn.execute("SELECT id, name FROM mcp_tools WHERE is_enabled = 1").fetchall()
        tool_ids = {row["name"]: row["id"] for row in tool_rows}

        for skill_name, tool_name in skill_specs.items():
            tool_id = tool_ids.get(tool_name) if tool_name else None
            conn.execute(
                "INSERT OR IGNORE INTO skills "
                "(name, description, prompt_template, mcp_tool_id) VALUES (?, ?, ?, ?)",
                (skill_name, f"{skill_name}任务能力",
                 f"你正在执行「{skill_name}」任务。请按用户目标完成任务，并仅在需要时调用已授权工具。",
                 tool_id),
            )
            if skills_created and tool_id:
                conn.execute(
                    "UPDATE skills SET mcp_tool_id = ? WHERE name = ? AND mcp_tool_id IS NULL",
                    (tool_id, skill_name),
                )

        skill_rows = conn.execute("SELECT id, name FROM skills").fetchall()
        skill_ids = {row["name"]: row["id"] for row in skill_rows}
        employees = conn.execute(
            "SELECT id, name, employee_type, skills, mcp_tool_ids FROM digital_employees"
        ).fetchall()
        for employee in employees:
            try:
                old_skills = json.loads(employee.get("skills") or "[]")
            except (json.JSONDecodeError, TypeError):
                old_skills = []
            if employees_created and old_skills and isinstance(old_skills[0], str):
                resolved = []
                for tag in old_skills:
                    skill_id = skill_ids.get(tag_to_skill.get(tag, tag))
                    if skill_id and skill_id not in resolved:
                        resolved.append(skill_id)
                conn.execute(
                    "UPDATE digital_employees SET skills = ? WHERE id = ?",
                    (json.dumps(resolved, ensure_ascii=False), employee["id"]),
                )

            # API 型员工使用 mcp_tool_id（单工具绑定），不参与 mcp_tool_ids 数组同步
            if employee.get("employee_type") == "api":
                continue

            names = employee_tools.get(employee["name"])
            current_tools = employee.get("mcp_tool_ids") or "[]"
            if employees_created and names and current_tools == "[]":
                resolved_tools = [tool_ids[name] for name in names if name in tool_ids]
                conn.execute(
                    "UPDATE digital_employees SET mcp_tool_ids = ? WHERE id = ?",
                    (json.dumps(resolved_tools, ensure_ascii=False), employee["id"]),
                )
