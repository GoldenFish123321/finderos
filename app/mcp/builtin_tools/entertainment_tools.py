"""
entertainment_tools.py — 娱乐类 MCP 工具处理函数

工具:
- get_random_music: 随机音乐推荐
"""

import logging
import random as _random
from typing import Any, Dict

logger = logging.getLogger(__name__)


async def _get_random_music() -> Dict[str, Any]:
    """随机获取一首歌曲（从网易云音乐热歌榜，通过统一出口）。当用户请求推荐或播放音乐时使用此工具。"""
    # 惰性 import 避免循环引用
    from app.services.local_api_client import call_local_api

    result = await call_local_api("music/netease", {})

    if result.get("success") and result.get("data"):
        songs = result["data"]
        if isinstance(songs, list) and len(songs) > 0:
            song = _random.choice(songs)
            return {
                "success": True,
                "name": song.get("name", ""),
                "artist": song.get("artist", ""),
                "cover": song.get("pic", ""),
                "url": song.get("url", ""),
                "source": "网易云音乐热歌榜",
            }

    # 回退到 mock 数据
    mock_songs = [
        {"name": "晴天", "artist": "周杰伦",
         "cover": "https://picsum.photos/seed/music1/160/160",
         "url": "https://music.163.com/"},
        {"name": "夜曲", "artist": "周杰伦",
         "cover": "https://picsum.photos/seed/music2/160/160",
         "url": "https://music.163.com/"},
        {"name": "稻香", "artist": "周杰伦",
         "cover": "https://picsum.photos/seed/music3/160/160",
         "url": "https://music.163.com/"},
    ]
    song = _random.choice(mock_songs)
    return {
        "success": True,
        "name": song["name"],
        "artist": song["artist"],
        "cover": song["cover"],
        "url": song["url"],
        "source": "本地曲库（Mock）",
        "note": f"API 调用失败: {result.get('error', '未知')[:100]}" if not result.get("success") else "",
    }


# ═══════════════════════════════════════════════════════════════
# music/netease handler — 统一对外出口
# ═══════════════════════════════════════════════════════════════

async def _music_netease_handler():
    """music/netease handler — 从网易云音乐热歌榜获取歌曲列表。"""
    import json as _json
    from app.utils.safe_http import safe_http_request, SafeHttpError

    url = "https://api.injahow.cn/meting/?server=netease&type=playlist&id=3778678"
    headers = {"User-Agent": "FinderOS/1.0", "Accept": "application/json"}
    try:
        resp = safe_http_request(
            url, headers=headers, timeout=15, max_bytes=1024 * 1024,
        )
        body = resp.body.decode("utf-8", errors="replace")
        songs = _json.loads(body)
        if isinstance(songs, list) and len(songs) > 0:
            return {"success": True, "data": songs}
        return {"success": False, "error": "歌曲列表为空"}
    except SafeHttpError as e:
        return {"success": False, "error": f"安全HTTP错误: {e}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── 自注册到 local_api_client ──
def _register_music_handler():
    from app.services.local_api_client import register_local_handler
    register_local_handler("music/netease", _music_netease_handler)


_register_music_handler()
