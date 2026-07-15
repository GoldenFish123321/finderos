"""
entertainment_tools.py — 娱乐类 MCP 工具处理函数

工具:
- get_random_music: 随机音乐推荐
"""

import asyncio
import logging
import random as _random
import urllib.request
import json as _json
from typing import Any, Dict

logger = logging.getLogger(__name__)


async def _get_random_music() -> Dict[str, Any]:
    """随机获取一首歌曲（从网易云音乐热歌榜）。"""

    def _sync_fetch():
        url = "https://api.injahow.cn/meting/?server=netease&type=playlist&id=3778678"
        headers = {"User-Agent": "FinderOS/1.0", "Accept": "application/json"}
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                songs = _json.loads(body)
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
                return {"success": False, "error": "歌曲列表为空"}
        except Exception as e:
            logger.warning(f"get_random_music 调用失败: {e}")
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
                "note": f"API 调用失败: {str(e)[:100]}",
            }

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_fetch)
