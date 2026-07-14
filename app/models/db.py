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
    return conn


@contextmanager
def get_db():
    """Context manager for database connections. Auto-commits and closes on exit."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
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
            conn.execute("ALTER TABLE ai_models ADD COLUMN total_tokens INTEGER DEFAULT 0")
            logger.info("Database migration: added total_tokens column to ai_models")
        except Exception:
            pass  # 列已存在

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
                (12, "AI对话", "layui-icon-dialogue", "/admin/model/chat", 3, 1, 1),
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
            # DeepSeek-V3（从环境变量读取 API Key）
            deepseek_key = os.environ.get("DEEPSEEK_API_KEY", "")
            if not deepseek_key:
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
    """种子：默认数字化员工（产业专员 + 天机助手）。"""
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
                    None,  # 自动使用默认模型
                    "你是一位专业的产业分析师，擅长：\n"
                    "1. 产业链结构分析与上下游关系梳理\n"
                    "2. 行业政策解读与趋势预判\n"
                    "3. 竞品分析与市场格局评估\n"
                    "4. 技术路线演进追踪\n"
                    "请用专业但不晦涩的语言回答，引用数据时注明来源。",
                    json.dumps(["产业分析", "政策解读", "竞品分析", "趋势预判"], ensure_ascii=False),
                    1,  # 启用 Crawl4ai 采集能力
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
            print("[种子] 默认数字化员工已创建（产业专员 + 天机助手）")
