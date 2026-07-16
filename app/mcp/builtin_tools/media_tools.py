"""
media_tools.py — AI 媒体生成 MCP 工具处理函数

工具:
- generate_image: AI 文生图（wan2.6-t2i）
- generate_video: AI 视频生成（wan2.6-t2v 文生视频 / wan2.6-i2v 图生视频）
"""

import asyncio
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


async def _generate_image(
    prompt: str,
    model_id: int = 0,
    size: str = "1024x1024",
    n: int = 1,
) -> Dict[str, Any]:
    """使用 AI 模型生成图片。当用户要求「画一张」「生成图片」「文生图」「create image」等时使用此工具。支持指定模型、尺寸和生成数量。

    Args:
        prompt: 图片描述/提示词
        model_id: 模型ID，填0或不填则使用系统默认图像模型
        size: 图片尺寸，如 1024x1024、512x512，默认 1024x1024
        n: 生成数量，默认 1
    """
    from app.models.ai_model import AiModelRepository
    from app.services.media_generator import call_image_gen_in_thread

    # 查找模型
    if model_id and model_id > 0:
        model = AiModelRepository.get_by_id(model_id)
    else:
        model = AiModelRepository.get_default_by_category("image")

    if not model:
        return {
            "success": False,
            "error": "没有可用的图像模型。请在后台「模型引擎」中配置 image 分类模型。",
        }

    api_base = (model.get("api_base") or "").strip()
    api_key = (model.get("api_key") or "").strip()
    model_name = (model.get("model_name") or model.get("name") or "").strip()

    if not api_base:
        return {"success": False, "error": f"图像模型「{model.get('name')}」未配置 API Base URL"}
    if not api_key:
        return {
            "success": False,
            "error": f"图像模型「{model.get('name')}」未配置 API Key。请在后台配置或联系管理员。",
        }

    # 在线程池中执行 HTTP 调用
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None,
            lambda: call_image_gen_in_thread(
                prompt=prompt,
                model_name=model_name,
                api_base=api_base,
                api_key=api_key,
                size=size,
                n=n,
            ),
        )
    except Exception as e:
        logger.error(f"图像生成异常: {e}", exc_info=True)
        return {"success": False, "error": f"图像生成失败: {str(e)}"}

    return result


async def _generate_video(
    prompt: str,
    model_id: int = 0,
    image_url: str = "",
) -> Dict[str, Any]:
    """使用 AI 模型生成视频。当用户要求「生成视频」「制作一段视频」「文生视频」「create video」等时使用此工具。支持文生视频和图生视频（通过 image_url 参数传入图片 URL）。

    Args:
        prompt: 视频描述/提示词
        model_id: 模型ID，填0或不填则使用系统默认视频模型
        image_url: 可选，图生视频时的输入图片 URL
    """
    from app.models.ai_model import AiModelRepository
    from app.services.media_generator import call_video_gen_in_thread

    # 查找模型
    if model_id and model_id > 0:
        model = AiModelRepository.get_by_id(model_id)
    else:
        model = AiModelRepository.get_default_by_category("video")

    if not model:
        return {
            "success": False,
            "error": "没有可用的视频模型。请在后台「模型引擎」中配置 video 分类模型。",
        }

    api_base = (model.get("api_base") or "").strip()
    api_key = (model.get("api_key") or "").strip()
    model_name = (model.get("model_name") or model.get("name") or "").strip()

    if not api_base:
        return {"success": False, "error": f"视频模型「{model.get('name')}」未配置 API Base URL"}
    if not api_key:
        return {
            "success": False,
            "error": f"视频模型「{model.get('name')}」未配置 API Key。请在后台配置或联系管理员。",
        }

    img_url = image_url.strip() if image_url and image_url.strip() else None

    # 在线程池中执行 HTTP 调用
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None,
            lambda: call_video_gen_in_thread(
                prompt=prompt,
                model_name=model_name,
                api_base=api_base,
                api_key=api_key,
                image_url=img_url,
            ),
        )
    except Exception as e:
        logger.error(f"视频生成异常: {e}", exc_info=True)
        return {"success": False, "error": f"视频生成失败: {str(e)}"}

    return result
