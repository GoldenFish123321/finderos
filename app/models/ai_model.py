"""
ai_model.py �?ai_models 表的仓储对象

模型引擎：管�?AI 模型配置（多 Provider、多分类、参数设置）�?"""
import sqlite3
from app.models.db import get_db

CATEGORIES = ["text", "image", "audio", "video", "multimodal", "embedding"]
PROVIDERS = ["openai", "deepseek", "qwen", "moonshot", "ollama", "zhipu", "baichuan"]


class AiModelRepository:
    """AI模型配置数据访问�?""

    @staticmethod
    def get_all(page: int = 1, page_size: int = 6,
                category: str = "") -> tuple:
        """分页查询模型列表，返�?(rows, total)�?""
        with get_db() as conn:
            if category and category in CATEGORIES:
                where = "WHERE category = ?"
                params = (category,)
            else:
                where = ""
                params = ()
            total = conn.execute(
                f"SELECT COUNT(*) as cnt FROM ai_models {where}", params
            ).fetchone()["cnt"]
            rows = conn.execute(
                f"SELECT * FROM ai_models {where} "
                f"ORDER BY is_default DESC, id ASC LIMIT ? OFFSET ?",
                (*params, page_size, (page - 1) * page_size),
            ).fetchall()
        return rows, total

    @staticmethod
    def get_by_id(model_id: int):
        """根据 ID 查询模型�?""
        with get_db() as conn:
            return conn.execute(
                "SELECT * FROM ai_models WHERE id = ?", (model_id,)
            ).fetchone()

    @staticmethod
    def get_default():
        """获取默认模型�?""
        with get_db() as conn:
            return conn.execute(
                "SELECT * FROM ai_models WHERE is_default = 1 AND is_enabled = 1 LIMIT 1"
            ).fetchone()

    @staticmethod
    def create(name: str, provider: str = "openai", api_base: str = "",
               api_key: str = "", model_name: str = "", category: str = "text",
               system_prompt: str = "", temperature: float = 0.7,
               top_p: float = 1.0, top_k: int = 50, max_tokens: int = 4096,
               context_size: int = 8192) -> int:
        """创建模型配置，返回新 ID�?""
        try:
            with get_db() as conn:
                cur = conn.execute(
                    "INSERT INTO ai_models (name, provider, api_base, api_key, model_name, "
                    "category, system_prompt, temperature, top_p, top_k, max_tokens, context_size) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (name.strip(), provider, api_base.strip(), api_key.strip(),
                     model_name.strip(), category, system_prompt.strip(),
                     temperature, top_p, top_k, max_tokens, context_size),
                )
                conn.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return -1

    @staticmethod
    def update(model_id: int, name: str, provider: str = "openai",
               api_base: str = "", api_key: str = "", model_name: str = "",
               category: str = "text", system_prompt: str = "",
               temperature: float = 0.7, top_p: float = 1.0,
               top_k: int = 50, max_tokens: int = 4096,
               context_size: int = 8192) -> bool:
        """更新模型配置�?""
        try:
            with get_db() as conn:
                conn.execute(
                    "UPDATE ai_models SET name=?, provider=?, api_base=?, api_key=?, "
                    "model_name=?, category=?, system_prompt=?, temperature=?, "
                    "top_p=?, top_k=?, max_tokens=?, context_size=? WHERE id=?",
                    (name.strip(), provider, api_base.strip(), api_key.strip(),
                     model_name.strip(), category, system_prompt.strip(),
                     temperature, top_p, top_k, max_tokens, context_size, model_id),
                )
                conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    @staticmethod
    def delete(model_id: int) -> bool:
        """删除模型配置�?""
        with get_db() as conn:
            conn.execute("DELETE FROM ai_models WHERE id = ?", (model_id,))
            conn.commit()
            return True

    @staticmethod
    def toggle_enabled(model_id: int) -> int:
        """切换启用/禁用，返回新状态�?""
        with get_db() as conn:
            row = conn.execute(
                "SELECT is_enabled FROM ai_models WHERE id = ?", (model_id,)
            ).fetchone()
            if not row:
                return -1
            new_status = 0 if row["is_enabled"] == 1 else 1
            conn.execute(
                "UPDATE ai_models SET is_enabled = ? WHERE id = ?",
                (new_status, model_id),
            )
            conn.commit()
            return new_status

    @staticmethod
    def set_default(model_id: int) -> bool:
        """设为默认模型（唯一约束：先�?0 再设 1）�?""
        with get_db() as conn:
            conn.execute("UPDATE ai_models SET is_default = 0")
            conn.execute(
                "UPDATE ai_models SET is_default = 1 WHERE id = ?", (model_id,)
            )
            conn.commit()
        return True

    @staticmethod
    def clear_tokens(model_id: int) -> bool:
        """清零 Token 计数�?
        占位方法：当前版本未持久�?Token 计数，仅返回 True�?        后续版本将在 ai_models 表中新增 token_usage 字段后实现真正的清零逻辑�?        """
        return True

    @staticmethod
    def get_count() -> int:
        """获取模型总数�?""
        with get_db() as conn:
            return conn.execute("SELECT COUNT(*) as cnt FROM ai_models").fetchone()["cnt"]

    @staticmethod
    def get_stats() -> dict:
        """获取模型引擎统计�?""
        with get_db() as conn:
            total = conn.execute("SELECT COUNT(*) as cnt FROM ai_models").fetchone()["cnt"]
            enabled = conn.execute(
                "SELECT COUNT(*) as cnt FROM ai_models WHERE is_enabled = 1"
            ).fetchone()["cnt"]
            has_default = conn.execute(
                "SELECT COUNT(*) as cnt FROM ai_models WHERE is_default = 1"
            ).fetchone()["cnt"]
        return {"total": total, "enabled": enabled, "has_default": has_default}
