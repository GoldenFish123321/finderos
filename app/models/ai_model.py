"""
ai_model.py - ai_models table repository (Repository pattern)
"""
import sqlite3
from app.models.db import get_db

# Model providers
PROVIDERS = [
    {"value": "openai", "name": "OpenAI"},
    {"value": "deepseek", "name": "DeepSeek"},
    {"value": "zhipu", "name": "Zhipu AI"},
    {"value": "baidu", "name": "Baidu Wenxin"},
    {"value": "custom", "name": "Custom"},
]

# Model categories
CATEGORIES = [
    {"value": "text", "name": "Text"},
    {"value": "vision", "name": "Vision"},
    {"value": "embedding", "name": "Embedding"},
]


class AiModelRepository:
    """AI model data access class."""

    @staticmethod
    def get_all(page: int = 1, page_size: int = 20, category: str = "") -> tuple:
        """Paginated query of AI models. Returns (rows, total)."""
        with get_db() as conn:
            conditions = []
            params = []
            if category:
                conditions.append("category = ?")
                params.append(category)
            where = "WHERE " + " AND ".join(conditions) if conditions else ""
            total = conn.execute(
                f"SELECT COUNT(*) as cnt FROM ai_models {where}", params
            ).fetchone()["cnt"]
            rows = conn.execute(
                f"SELECT * FROM ai_models {where} ORDER BY is_default DESC, id ASC "
                f"LIMIT ? OFFSET ?",
                (*params, page_size, (page - 1) * page_size),
            ).fetchall()
        return rows, total

    @staticmethod
    def get_by_id(model_id: int):
        """Get AI model by ID."""
        with get_db() as conn:
            return conn.execute(
                "SELECT * FROM ai_models WHERE id = ?", (model_id,)
            ).fetchone()

    @staticmethod
    def get_default():
        """Get the default model."""
        with get_db() as conn:
            return conn.execute(
                "SELECT * FROM ai_models WHERE is_default = 1 AND is_enabled = 1 LIMIT 1"
            ).fetchone()

    @staticmethod
    def create(name: str, provider: str = "openai", api_base: str = "",
               api_key: str = "", model_name: str = "", category: str = "text",
               system_prompt: str = "", temperature: float = 0.7,
               top_p: float = 1.0, top_k: int = 50,
               max_tokens: int = 4096, context_size: int = 8192) -> int:
        """Create an AI model. Returns new ID."""
        try:
            with get_db() as conn:
                cur = conn.execute(
                    "INSERT INTO ai_models (name, provider, api_base, api_key, model_name, "
                    "category, system_prompt, temperature, top_p, top_k, max_tokens, context_size) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (name.strip(), provider.strip(), api_base.strip(), api_key.strip(),
                     model_name.strip(), category.strip(), system_prompt, temperature,
                     top_p, top_k, max_tokens, context_size),
                )
                conn.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return -1

    @staticmethod
    def update(model_id: int, name: str, provider: str = "openai", api_base: str = "",
               api_key: str = "", model_name: str = "", category: str = "text",
               system_prompt: str = "", temperature: float = 0.7,
               top_p: float = 1.0, top_k: int = 50,
               max_tokens: int = 4096, context_size: int = 8192) -> bool:
        """Update an AI model."""
        try:
            with get_db() as conn:
                if api_key:
                    conn.execute(
                        "UPDATE ai_models SET name=?, provider=?, api_base=?, api_key=?, "
                        "model_name=?, category=?, system_prompt=?, temperature=?, "
                        "top_p=?, top_k=?, max_tokens=?, context_size=? WHERE id=?",
                        (name.strip(), provider.strip(), api_base.strip(), api_key.strip(),
                         model_name.strip(), category.strip(), system_prompt, temperature,
                         top_p, top_k, max_tokens, context_size, model_id),
                    )
                else:
                    conn.execute(
                        "UPDATE ai_models SET name=?, provider=?, api_base=?, "
                        "model_name=?, category=?, system_prompt=?, temperature=?, "
                        "top_p=?, top_k=?, max_tokens=?, context_size=? WHERE id=?",
                        (name.strip(), provider.strip(), api_base.strip(),
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
            conn.execute("DELETE FROM ai_models WHERE id = ?", (model_id,))
            conn.commit()
            return conn.total_changes > 0

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
        """Set a model as default (unique: clear all then set one)."""
        with get_db() as conn:
            conn.execute("UPDATE ai_models SET is_default = 0")
            conn.execute(
                "UPDATE ai_models SET is_default = 1 WHERE id = ?", (model_id,)
            )
            conn.commit()
        return True

    @staticmethod
    def clear_tokens(model_id: int) -> bool:
        """Clear token count (placeholder - not yet implemented)."""
        return True

    @staticmethod
    def get_count() -> int:
        """Get total model count."""
        with get_db() as conn:
            return conn.execute("SELECT COUNT(*) as cnt FROM ai_models").fetchone()["cnt"]

    @staticmethod
    def get_stats() -> dict:
        """Get model engine statistics."""
        with get_db() as conn:
            total = conn.execute("SELECT COUNT(*) as cnt FROM ai_models").fetchone()["cnt"]
            enabled = conn.execute(
                "SELECT COUNT(*) as cnt FROM ai_models WHERE is_enabled = 1"
            ).fetchone()["cnt"]
            has_default = conn.execute(
                "SELECT COUNT(*) as cnt FROM ai_models WHERE is_default = 1"
            ).fetchone()["cnt"]
            return {"total": total, "enabled": enabled, "has_default": has_default}
