"""本地接口注册表 — 将系统内置接口元数据同步到 api_interfaces 表。"""

import logging
from app.models.db import get_db

logger = logging.getLogger(__name__)

LOCAL_API_SEEDS = [
    # ── 数据仓库 ──
    {"name": "搜索数据仓库", "handler": "warehouse/search", "desc": "按关键词搜索数据仓库内容。"},
    {"name": "获取最新数据", "handler": "warehouse/recent", "desc": "获取数据仓库中最新入库的数据。"},
    {"name": "数据仓库统计", "handler": "warehouse/stats", "desc": "获取数据仓库的统计信息（总条数、分类分布等）。"},
    {"name": "全文搜索", "handler": "warehouse/fulltext", "desc": "对数据仓库执行全文搜索（FTS5）。"},
    {"name": "按ID查询", "handler": "warehouse/by_id", "desc": "根据ID精确查询数据仓库中的单条记录。"},
    # ── 采集 ──
    {"name": "网页数据采集", "handler": "collect/web", "desc": "采集指定网页的数据（HTTP抓取+解析）。"},
    {"name": "深度网页采集", "handler": "collect/deep", "desc": "对单条URL执行深度网页内容采集。"},
    {"name": "瞭源列表", "handler": "collect/sources", "desc": "列出所有已配置的瞭望采集源。"},
    # ── 数字员工 ──
    {"name": "员工列表", "handler": "employee/list", "desc": "列出所有可用的数字员工。"},
    {"name": "调用员工", "handler": "employee/invoke", "desc": "调用指定的数字员工执行任务。"},
    # ── AI模型 ──
    {"name": "模型列表", "handler": "model/list", "desc": "列出所有已配置的AI模型。"},
    {"name": "获取默认模型", "handler": "model/default", "desc": "获取系统默认的AI模型配置。"},
    # ── 对话 ──
    {"name": "对话列表", "handler": "conversation/list", "desc": "列出当前用户的所有对话。"},
    {"name": "对话消息", "handler": "conversation/messages", "desc": "获取指定对话的所有消息记录。"},
    # ── Crawl4ai ──
    {"name": "Crawl4ai采集", "handler": "crawl4ai/collect", "desc": "使用Crawl4ai引擎采集网页内容。"},
    {"name": "Crawl4ai批量", "handler": "crawl4ai/batch", "desc": "使用Crawl4ai引擎批量采集多个URL。"},
    # ── AI媒体生成 ──
    {"name": "AI图像生成", "handler": "media/generate_image", "desc": "使用AI模型生成图片。"},
    {"name": "AI视频生成", "handler": "media/generate_video", "desc": "使用AI模型生成视频。"},
    # ── 系统 ──
    {"name": "系统状态", "handler": "system/stats", "desc": "获取系统的运行状态和资源使用情况。"},
    {"name": "加载技能", "handler": "skill/load", "desc": "加载指定的系统技能模块。"},
    # ── 统一对外出口（方案B新增）──
    {"name": "瞭望采集", "handler": "collector/fetch", "desc": "根据瞭源ID和关键词采集网页HTML（统一对外出口）。"},
    {"name": "深度采集", "handler": "collector/deep-fetch", "desc": "采集任意URL的网页HTML内容（统一对外出口）。"},
    {"name": "网易云音乐", "handler": "music/netease", "desc": "从网易云音乐热歌榜获取推荐歌曲列表（统一对外出口）。"},
]

# ── 外部接口种子数据 ──
# 这些 external 类型接口可在管理后台"接口管理"页面中查看和管理。
EXTERNAL_API_SEEDS = [
    {
        "name": "网易云音乐热歌榜",
        "api_url": "https://api.injahow.cn/meting/?server=netease&type=playlist&id=3778678",
        "api_method": "GET",
        "interface_type": "external",
        "is_system": 0,
        "is_enabled": 1,
        "response_content_type": "json",
        "description": "从网易云音乐热歌榜获取推荐歌曲列表（外部API接口）。",
    },
]


def sync_local_api_interfaces():
    """将本地和外部接口种子幂等同步到 api_interfaces 表。"""
    with get_db() as conn:
        # ── 本地接口 ──
        for seed in LOCAL_API_SEEDS:
            existing = conn.execute(
                "SELECT id FROM api_interfaces WHERE local_handler = ?", (seed["handler"],)
            ).fetchone()
            if existing:
                # 已存在，只更新名称和描述
                conn.execute(
                    "UPDATE api_interfaces SET name = ?, description = ?, is_enabled = 1 "
                    "WHERE local_handler = ?",
                    (seed["name"], seed["desc"], seed["handler"]),
                )
            else:
                conn.execute(
                    """INSERT INTO api_interfaces
                    (name, description, api_url, api_method, api_headers, api_params_template,
                     interface_type, is_system, local_handler, is_enabled, sort_order)
                    VALUES (?, ?, 'local://', 'GET', '{}', '{}', 'local', 1, ?, 1, 0)""",
                    (seed["name"], seed["desc"], seed["handler"]),
                )

        # ── 外部接口 ──
        for seed in EXTERNAL_API_SEEDS:
            existing = conn.execute(
                "SELECT id FROM api_interfaces WHERE name = ? AND interface_type = 'external'",
                (seed["name"],),
            ).fetchone()
            if existing:
                # 已存在，更新 URL 等字段
                conn.execute(
                    """UPDATE api_interfaces SET
                        api_url = ?, api_method = ?, description = ?,
                        response_content_type = ?, is_enabled = ?, is_system = ?
                    WHERE id = ?""",
                    (
                        seed["api_url"],
                        seed["api_method"],
                        seed.get("description", ""),
                        seed.get("response_content_type", "json"),
                        seed.get("is_enabled", 1),
                        seed.get("is_system", 0),
                        existing["id"],
                    ),
                )
            else:
                conn.execute(
                    """INSERT INTO api_interfaces
                    (name, description, api_url, api_method, api_headers, api_params_template,
                     interface_type, is_system, local_handler, response_content_type,
                     is_enabled, sort_order)
                    VALUES (?, ?, ?, ?, '{}', '', ?, ?, '', ?, ?, 0)""",
                    (
                        seed["name"],
                        seed.get("description", ""),
                        seed["api_url"],
                        seed["api_method"],
                        seed["interface_type"],
                        seed.get("is_system", 0),
                        seed.get("response_content_type", "json"),
                        seed.get("is_enabled", 1),
                    ),
                )
        conn.commit()
    logger.info(f"已同步 {len(LOCAL_API_SEEDS)} 个本地接口 + {len(EXTERNAL_API_SEEDS)} 个外部接口到 api_interfaces 表")
