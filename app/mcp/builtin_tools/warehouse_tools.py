"""
warehouse_tools.py — 数据仓库类 MCP 工具处理函数

工具:
- search_warehouse: 关键词搜索
- get_recent_warehouse_data: 最新数据
- get_warehouse_stats: 统计概况
- search_warehouse_fulltext: FTS5 全文检索 (v0.6.0 新增)
"""

from typing import Any, Dict


def _search_warehouse(keyword: str, limit: int = 10) -> Dict[str, Any]:
    """在数据仓库中搜索关键词相关内容。"""
    from app.models.data_warehouse import DataWarehouseRepository
    items = DataWarehouseRepository.search(keyword, limit=limit)
    return {
        "total": len(items),
        "items": [
            {
                "id": it.get("id"),
                "title": it.get("title", ""),
                "summary": (it.get("summary", "") or "")[:300],
                "source_name": it.get("source_name", ""),
                "link": it.get("link", ""),
                "created_at": it.get("created_at", ""),
            }
            for it in items
        ],
    }


def _get_recent_warehouse_data(limit: int = 10) -> Dict[str, Any]:
    """获取数据仓库中最新入库的数据。"""
    from app.models.data_warehouse import DataWarehouseRepository
    items = DataWarehouseRepository.get_recent(limit=limit)
    return {
        "total": len(items),
        "items": [
            {
                "id": it.get("id"),
                "title": it.get("title", ""),
                "summary": (it.get("summary", "") or "")[:300],
                "source_name": it.get("source_name", ""),
                "link": it.get("link", ""),
                "is_deep_collected": bool(it.get("is_deep_collected", 0)),
                "created_at": it.get("created_at", ""),
            }
            for it in items
        ],
    }


def _get_warehouse_stats() -> Dict[str, Any]:
    """获取数据仓库的统计信息。"""
    from app.models.data_warehouse import DataWarehouseRepository
    stats = DataWarehouseRepository.get_stats()
    return stats if stats else {"total": 0, "deep_collected": 0, "top_sources": []}


def _search_warehouse_fulltext(query: str, limit: int = 10) -> Dict[str, Any]:
    """使用 FTS5 对数据仓库进行全文检索（v0.6.0 新增）。
    
    如果 FTS5 不可用，回退到普通搜索。
    """
    from app.models.data_warehouse import DataWarehouseRepository
    from app.models.db import get_db
    try:
        # 尝试 FTS5 搜索
        with get_db() as conn:
            rows = conn.execute(
                "SELECT d.* FROM data_warehouse d "
                "JOIN data_warehouse_fts f ON d.id = f.rowid "
                "WHERE data_warehouse_fts MATCH ? "
                "ORDER BY rank LIMIT ?",
                (query, limit),
            ).fetchall()
        items = [dict(r) for r in rows]
        return {
            "total": len(items),
            "query": query,
            "items": [
                {
                    "id": it.get("id"),
                    "title": it.get("title", ""),
                    "summary": (it.get("summary", "") or "")[:300],
                    "source_name": it.get("source_name", ""),
                    "link": it.get("link", ""),
                    "created_at": it.get("created_at", ""),
                }
                for it in items
            ],
        }
    except Exception:
        # 回退到普通搜索
        items = DataWarehouseRepository.search(query, limit=limit)
        return {
            "total": len(items),
            "query": query,
            "method": "fallback_keyword_search",
            "items": [
                {
                    "id": it.get("id"),
                    "title": it.get("title", ""),
                    "summary": (it.get("summary", "") or "")[:300],
                    "source_name": it.get("source_name", ""),
                    "link": it.get("link", ""),
                    "created_at": it.get("created_at", ""),
                }
                for it in items
            ],
        }
