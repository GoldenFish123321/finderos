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


def get_connection() -> sqlite3.Connection:
    """Get a new database connection. Caller is responsible for closing."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
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
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 兼容旧表迁移：为已存在的 ai_models 表添加 total_tokens 列
        try:
            cols = {row[1] for row in conn.execute("PRAGMA table_info(ai_models)").fetchall()}
            if "total_tokens" not in cols:
                conn.execute("ALTER TABLE ai_models ADD COLUMN total_tokens INTEGER DEFAULT 0")
                logger.info("Database migration: added total_tokens column to ai_models")
        except Exception as e:
            logger.error(f"Database migration failed (ai_models.total_tokens): {e}", exc_info=True)

        # 兼容旧表迁移：为已存在的 watch_sources 表添加 schedule_interval 列 (v0.6.0)
        try:
            cols = {row[1] for row in conn.execute("PRAGMA table_info(watch_sources)").fetchall()}
            if "schedule_interval" not in cols:
                conn.execute("ALTER TABLE watch_sources ADD COLUMN schedule_interval INTEGER DEFAULT 0")
                logger.info("Database migration: added schedule_interval column to watch_sources")
        except Exception as e:
            logger.error(f"Database migration failed (watch_sources.schedule_interval): {e}", exc_info=True)

        # 独立数据仓库表（v0.2.13 新增，借鉴郭家琪项目的独立设计）
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

        # 数字化员工表 (v0.3.0 新增)
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
                -- API 型字段
                api_url                 TEXT DEFAULT '',
                api_method              TEXT DEFAULT 'GET',
                api_headers             TEXT DEFAULT '{}',
                api_params_template     TEXT DEFAULT '',
                response_render_template TEXT DEFAULT '',
                api_secret              TEXT DEFAULT '',
                -- 通用字段
                is_enabled              INTEGER DEFAULT 1,
                created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (model_id) REFERENCES ai_models(id) ON DELETE SET NULL
            )
        """)

        # 对话管理表 (v0.5.0 新增 — 多轮对话支持)
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
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_conv_msgs_conv ON conversation_messages(conversation_id)")

        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_role_id ON users(role_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_functions_parent ON functions(parent_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_role_functions_role ON role_functions(role_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_role_functions_func ON role_functions(function_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_watch_sources_enabled ON watch_sources(is_enabled)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_watch_results_source ON watch_results(source_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_models_default ON ai_models(is_default)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_username ON audit_logs(username)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_created ON audit_logs(created_at)")

        conn.commit()
        logger.info(f"Database initialized: {DB_PATH}")


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
                (2, "普通用户", "普通用户角色，仅可登录前台用户侧", 1),
            )
            print("[种子] 默认角色已创建")

        existing_admin = conn.execute(
            "SELECT COUNT(*) as cnt FROM users WHERE username = ?", ("admin",)
        ).fetchone()
        if existing_admin["cnt"] == 0:
            salt = secrets.token_bytes(16)
            dk = hashlib.pbkdf2_hmac("sha256", "admin888".encode(), salt, settings.PBKDF2_ITERATIONS)
            conn.execute(
                "INSERT INTO users (username, password_hash, salt, role_id, is_enabled) VALUES (?, ?, ?, ?, ?)",
                ("admin", dk.hex(), salt.hex(), 1, 1),
            )
            print("[种子] 默认管理员 admin 已创建 (密码: admin888)")

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
                (11, "模型引擎", "layui-icon-util", "/admin/model", None, 7, 1),
                # 系统设置子项（新增，借鉴陈子墨丰富的种子数据设计）
                (12, "AI对话", "layui-icon-dialogue", "/chat", 3, 1, 1),
                # 数字员工 (v0.3.0 新增)
                (13, "数字员工", "layui-icon-user", "/admin/employee", None, 8, 1),
            ]
            conn.executemany(
                "INSERT INTO functions (id, name, icon, route_path, parent_id, sort_order, is_enabled) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                functions,
            )
            print("[种子] 默认功能模块已创建")

        existing_rf = conn.execute("SELECT COUNT(*) as cnt FROM role_functions").fetchone()
        if existing_rf["cnt"] == 0:
            func_ids = conn.execute("SELECT id FROM functions WHERE is_enabled = 1").fetchall()
            conn.executemany(
                "INSERT INTO role_functions (role_id, function_id) VALUES (?, ?)",
                [(1, row["id"]) for row in func_ids],
            )
            print("[种子] 管理员角色功能关联已创建")

        conn.commit()

    _seed_default_sources()
    _seed_default_models()
    _seed_default_employees()


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
            # 文本模型
            conn.execute(
                "INSERT INTO ai_models (id, name, provider, api_base, model_name, category, is_enabled, is_default) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (1, "GPT-4o-mini", "openai", "https://api.openai.com/v1", "gpt-4o-mini", "text", 1, 1),
            )
            # DeepSeek-V3（从环境变量读取 API Key，加密存储）
            deepseek_key = os.environ.get("DEEPSEEK_API_KEY", "")
            if deepseek_key:
                from app.utils.security import encrypt_api_key
                deepseek_key = encrypt_api_key(deepseek_key)
            else:
                print("[种子] 提示: DEEPSEEK_API_KEY 未设置，DeepSeek 模型将使用 Mock 模式")
            conn.execute(
                "INSERT INTO ai_models (id, name, provider, api_base, api_key, model_name, category, is_enabled, is_default) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (2, "DeepSeek-V3", "deepseek", "https://api.deepseek.com", deepseek_key,
                 "deepseek-chat", "text", 1, 0),
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
            print("[种子] 默认AI模型已创建（6个模型，覆盖6种分类）")


def _seed_default_employees():
    """种子：默认数字化员工（产业专员 + 天机助手 + 天气 + 采集专员 + 文案编写 + 新闻聚合 + 科普助手）。"""
    import json
    with get_db() as conn:
        existing = conn.execute("SELECT COUNT(*) as cnt FROM digital_employees").fetchone()
        if existing["cnt"] == 0:
            # 产业专员 — LLM 型数字员工
            conn.execute(
                "INSERT INTO digital_employees (id, name, employee_type, description, "
                "model_id, system_prompt, skills, crawl4ai_enabled, is_enabled) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                    1,
                ),
            )
            # 天机助手 — LLM 型数字员工
            conn.execute(
                "INSERT INTO digital_employees (id, name, employee_type, description, "
                "model_id, system_prompt, skills, crawl4ai_enabled, is_enabled) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                    1,
                ),
            )
            # 天气查询 — API 型数字员工（免费天气 API）
            conn.execute(
                "INSERT INTO digital_employees (id, name, employee_type, description, "
                "api_url, api_method, api_headers, api_params_template, response_render_template, is_enabled) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    3, "天气", "api",
                    "查询指定城市的天气信息，返回温度、天气状况、风力等",
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
                ),
            )
            # 采集专员 — LLM 型数字员工（带 Crawl4ai 深度采集）
            conn.execute(
                "INSERT INTO digital_employees (id, name, employee_type, description, "
                "model_id, system_prompt, skills, crawl4ai_enabled, is_enabled) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                    1,
                    1,
                ),
            )
            # 文案编写 — LLM 型数字员工
            conn.execute(
                "INSERT INTO digital_employees (id, name, employee_type, description, "
                "model_id, system_prompt, skills, crawl4ai_enabled, is_enabled) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                    1,
                ),
            )
            # 新闻聚合 — LLM 型数字员工
            conn.execute(
                "INSERT INTO digital_employees (id, name, employee_type, description, "
                "model_id, system_prompt, skills, crawl4ai_enabled, is_enabled) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                    1,
                ),
            )
            # 科普助手 — LLM 型数字员工
            conn.execute(
                "INSERT INTO digital_employees (id, name, employee_type, description, "
                "model_id, system_prompt, skills, crawl4ai_enabled, is_enabled) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                    1,
                ),
            )
            print("[种子] 默认数字化员工已创建（7个：产业专员/天机助手/天气/采集专员/文案编写/新闻聚合/科普助手）")
