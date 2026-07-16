"""
ai_model.py - ai_models table repository (Repository pattern)
"""
import logging
import sqlite3
from app.models.db import get_db
from app.utils.security import encrypt_api_key, decrypt_api_key

logger = logging.getLogger(__name__)

# Model providers
PROVIDERS = [
    {"value": "openai", "name": "OpenAI"},
    {"value": "deepseek", "name": "DeepSeek"},
    {"value": "zhipu", "name": "Zhipu AI"},
    {"value": "baidu", "name": "Baidu Wenxin"},
    {"value": "custom", "name": "Custom"},
]

# Model categories (扩展到6种，借鉴冯凯乐/陈子墨)
CATEGORIES = [
    {"value": "text", "name": "Text"},
    {"value": "image", "name": "Image"},
    {"value": "audio", "name": "Audio"},
    {"value": "video", "name": "Video"},
    {"value": "multimodal", "name": "Multimodal"},
    {"value": "embedding", "name": "Embedding"},
]


class AiModelRepository:
    """AI model data access class."""

    @staticmethod
    def _row_to_dict(row, include_api_key: bool = False) -> dict:
        row_dict = dict(row)
        row_dict.setdefault("model_scope", "admin")
        row_dict.setdefault("owner_username", "")
        row_dict["has_api_key"] = bool(row_dict.get("api_key"))
        row_dict["api_key"] = (
            decrypt_api_key(row_dict.get("api_key", "")) if include_api_key else ""
        )
        return row_dict

    @staticmethod
    def get_all(page: int = 1, page_size: int = 20, category: str = "",
                enabled_only: bool = False, include_api_key: bool = False,
                model_scope: str = "", owner_username: str | None = None) -> tuple:
        """Paginated query of AI models. Returns (rows, total)."""
        with get_db() as conn:
            conditions = []
            params = []
            if category:
                conditions.append("category = ?")
                params.append(category)
            if enabled_only:
                conditions.append("is_enabled = 1")
            if model_scope:
                conditions.append("COALESCE(model_scope, 'admin') = ?")
                params.append(model_scope)
            if owner_username is not None:
                conditions.append("COALESCE(owner_username, '') = ?")
                params.append(owner_username)
            where = "WHERE " + " AND ".join(conditions) if conditions else ""
            total = conn.execute(
                f"SELECT COUNT(*) as cnt FROM ai_models {where}", params
            ).fetchone()["cnt"]
            rows = conn.execute(
                f"SELECT * FROM ai_models {where} ORDER BY is_default DESC, id ASC "
                f"LIMIT ? OFFSET ?",
                (*params, page_size, (page - 1) * page_size),
            ).fetchall()
        return [AiModelRepository._row_to_dict(row, include_api_key) for row in rows], total

    @staticmethod
    def get_by_id(model_id: int, include_api_key: bool = False):
        """Get AI model by ID."""
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM ai_models WHERE id = ?", (model_id,)
            ).fetchone()
        if row:
            return AiModelRepository._row_to_dict(row, include_api_key)
        return None

    @staticmethod
    def get_default(include_api_key: bool = False, model_scope: str = "admin",
                    owner_username: str = ""):
        """Get the default model in a model group."""
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM ai_models "
                "WHERE is_default = 1 AND is_enabled = 1 "
                "AND COALESCE(model_scope, 'admin') = ? "
                "AND COALESCE(owner_username, '') = ? "
                "LIMIT 1",
                (model_scope, owner_username),
            ).fetchone()
        if row:
            return AiModelRepository._row_to_dict(row, include_api_key)
        return None

    @staticmethod
    def get_accessible_by_id(model_id: int, username: str = "",
                             include_api_key: bool = False):
        """Get an admin model or the current user's private model by ID."""
        model = AiModelRepository.get_by_id(model_id, include_api_key=include_api_key)
        if not model:
            return None
        if model.get("model_scope", "admin") == "admin":
            return model
        if model.get("model_scope") == "user" and model.get("owner_username", "") == username:
            return model
        return None

    @staticmethod
    def get_default_for_user(username: str, include_api_key: bool = False):
        """Prefer current user's default model, then admin default, then first enabled accessible model."""
        user_model = AiModelRepository.get_default(
            include_api_key=include_api_key, model_scope="user", owner_username=username
        )
        if user_model:
            return user_model
        admin_model = AiModelRepository.get_default(
            include_api_key=include_api_key, model_scope="admin", owner_username=""
        )
        if admin_model:
            return admin_model
        models, _ = AiModelRepository.get_available_for_user(
            username, page=1, page_size=1, include_api_key=include_api_key
        )
        return models[0] if models else None

    @staticmethod
    def get_available_for_user(username: str, page: int = 1, page_size: int = 50,
                               include_api_key: bool = False) -> tuple:
        """Return enabled user-private models plus enabled admin-provided models."""
        offset = (page - 1) * page_size
        with get_db() as conn:
            params = (username,)
            total = conn.execute(
                "SELECT COUNT(*) as cnt FROM ai_models "
                "WHERE is_enabled = 1 AND ("
                "COALESCE(model_scope, 'admin') = 'admin' "
                "OR (COALESCE(model_scope, 'admin') = 'user' AND COALESCE(owner_username, '') = ?)"
                ")",
                params,
            ).fetchone()["cnt"]
            rows = conn.execute(
                "SELECT * FROM ai_models "
                "WHERE is_enabled = 1 AND ("
                "COALESCE(model_scope, 'admin') = 'admin' "
                "OR (COALESCE(model_scope, 'admin') = 'user' AND COALESCE(owner_username, '') = ?)"
                ") "
                "ORDER BY CASE COALESCE(model_scope, 'admin') WHEN 'user' THEN 0 ELSE 1 END, "
                "is_default DESC, id ASC LIMIT ? OFFSET ?",
                (username, page_size, offset),
            ).fetchall()
        return [AiModelRepository._row_to_dict(row, include_api_key) for row in rows], total

    @staticmethod
    def create(name: str, provider: str = "deepseek", api_base: str = "",
               api_key: str = "", model_name: str = "", category: str = "text",
               system_prompt: str = "", temperature: float = 0.7,
               top_p: float = 1.0, top_k: int = 50,
               max_tokens: int = 4096, context_size: int = 8192,
               model_scope: str = "admin", owner_username: str = "") -> int:
        """Create an AI model. Returns new ID. api_key 自动加密存储。"""
        try:
            encrypted_key = encrypt_api_key(api_key.strip()) if api_key else ""
            model_scope = model_scope if model_scope in ("admin", "user") else "admin"
            owner_username = owner_username.strip() if model_scope == "user" else ""
            with get_db() as conn:
                cur = conn.execute(
                    "INSERT INTO ai_models (name, provider, api_base, api_key, model_name, "
                    "category, system_prompt, temperature, top_p, top_k, max_tokens, context_size, "
                    "model_scope, owner_username) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (name.strip(), provider.strip(), api_base.strip(), encrypted_key,
                     model_name.strip(), category.strip(), system_prompt, temperature,
                     top_p, top_k, max_tokens, context_size, model_scope, owner_username),
                )
                conn.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return -1

    @staticmethod
    def update(model_id: int, name: str, provider: str = "deepseek", api_base: str = "",
               api_key: str = "", model_name: str = "", category: str = "text",
               system_prompt: str = "", temperature: float = 0.7,
               top_p: float = 1.0, top_k: int = 50,
               max_tokens: int = 4096, context_size: int = 8192) -> bool:
        """Update an AI model. api_key 自动加密存储。

        注意: api_key 传空字符串会清空数据库中已有的 API Key（允许用户清除敏感凭证）。
        """
        try:
            encrypted_key = encrypt_api_key(api_key.strip()) if api_key else ""
            with get_db() as conn:
                conn.execute(
                    "UPDATE ai_models SET name=?, provider=?, api_base=?, api_key=?, "
                    "model_name=?, category=?, system_prompt=?, temperature=?, "
                    "top_p=?, top_k=?, max_tokens=?, context_size=? WHERE id=?",
                    (name.strip(), provider.strip(), api_base.strip(), encrypted_key,
                     model_name.strip(), category.strip(), system_prompt, temperature,
                     top_p, top_k, max_tokens, context_size, model_id),
                )
                conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    @staticmethod
    def delete(model_id: int) -> bool:
        """Delete an AI model."""
        with get_db() as conn:
            cursor = conn.execute("DELETE FROM ai_models WHERE id = ?", (model_id,))
            conn.commit()
            return cursor.rowcount > 0

    @staticmethod
    def toggle_enabled(model_id: int) -> int:
        """Toggle model enabled/disabled. Returns new status (0/1) or -1."""
        with get_db() as conn:
            row = conn.execute(
                "SELECT is_enabled FROM ai_models WHERE id = ?", (model_id,)
            ).fetchone()
            if not row:
                return -1
            new_status = 0 if row["is_enabled"] == 1 else 1
            conn.execute(
                "UPDATE ai_models SET is_enabled = ? WHERE id = ?", (new_status, model_id)
            )
            if new_status == 0:
                conn.execute(
                    "UPDATE ai_models SET is_default = 0 WHERE id = ?", (model_id,)
                )
            conn.commit()
            return new_status

    @staticmethod
    def set_default(model_id: int) -> bool:
        """Set a model as default inside its own group (admin or per-user)."""
        with get_db() as conn:
            row = conn.execute(
                "SELECT COALESCE(model_scope, 'admin') as model_scope, "
                "COALESCE(owner_username, '') as owner_username "
                "FROM ai_models WHERE id = ?",
                (model_id,),
            ).fetchone()
            if not row:
                return False
            conn.execute(
                "UPDATE ai_models SET is_default = 0 "
                "WHERE COALESCE(model_scope, 'admin') = ? "
                "AND COALESCE(owner_username, '') = ?",
                (row["model_scope"], row["owner_username"]),
            )
            conn.execute(
                "UPDATE ai_models SET is_default = 1 WHERE id = ?", (model_id,)
            )
            conn.commit()
        return True

    @staticmethod
    def add_tokens(model_id: int, tokens: int) -> bool:
        """累加 Token 消耗量。"""
        try:
            with get_db() as conn:
                conn.execute(
                    "UPDATE ai_models SET total_tokens = total_tokens + ? WHERE id = ?",
                    (tokens, model_id),
                )
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"add_tokens: 更新模型 {model_id} Token 计数失败: {e}", exc_info=True)
            return False

    @staticmethod
    def clear_tokens(model_id: int) -> bool:
        """清零 Token 计数。"""
        with get_db() as conn:
            conn.execute(
                "UPDATE ai_models SET total_tokens = 0 WHERE id = ?", (model_id,)
            )
            conn.commit()
        return True

    @staticmethod
    def get_token_stats() -> dict:
        """获取 Token 消耗统计。"""
        with get_db() as conn:
            total = conn.execute(
                "SELECT COALESCE(SUM(total_tokens), 0) as cnt FROM ai_models"
            ).fetchone()["cnt"]
            return {"total_tokens": total}

    @staticmethod
    def get_count(model_scope: str = "", owner_username: str | None = None) -> int:
        """Get total model count."""
        with get_db() as conn:
            conditions = []
            params = []
            if model_scope:
                conditions.append("COALESCE(model_scope, 'admin') = ?")
                params.append(model_scope)
            if owner_username is not None:
                conditions.append("COALESCE(owner_username, '') = ?")
                params.append(owner_username)
            where = "WHERE " + " AND ".join(conditions) if conditions else ""
            return conn.execute(
                f"SELECT COUNT(*) as cnt FROM ai_models {where}", params
            ).fetchone()["cnt"]

    @staticmethod
    def get_stats(model_scope: str = "", owner_username: str | None = None) -> dict:
        """Get model engine statistics."""
        with get_db() as conn:
            conditions = []
            params = []
            if model_scope:
                conditions.append("COALESCE(model_scope, 'admin') = ?")
                params.append(model_scope)
            if owner_username is not None:
                conditions.append("COALESCE(owner_username, '') = ?")
                params.append(owner_username)
            where = "WHERE " + " AND ".join(conditions) if conditions else ""
            total = conn.execute(
                f"SELECT COUNT(*) as cnt FROM ai_models {where}", params
            ).fetchone()["cnt"]
            enabled_conditions = conditions + ["is_enabled = 1"]
            enabled_where = "WHERE " + " AND ".join(enabled_conditions)
            enabled = conn.execute(
                f"SELECT COUNT(*) as cnt FROM ai_models {enabled_where}", params
            ).fetchone()["cnt"]
            default_conditions = conditions + ["is_default = 1"]
            default_where = "WHERE " + " AND ".join(default_conditions)
            has_default = conn.execute(
                f"SELECT COUNT(*) as cnt FROM ai_models {default_where}", params
            ).fetchone()["cnt"]
            return {"total": total, "enabled": enabled, "has_default": has_default}
