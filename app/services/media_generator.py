"""
media_generator.py — AI 媒体生成服务

提供图像生成（文生图 / 图生图）和视频生成（文生视频 / 图生视频）的统一 HTTP 调用层。
所有调用使用 safe_http_request，在线程池中执行以避免阻塞 IOLoop。
视频生成后立即代理下载到本地，提供稳定访问 URL（OSS 签名链接有时效）。
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any, Dict, List, Optional, Tuple

from app.utils.safe_http import safe_http_request, SafeHttpError
from app.utils.security import validate_url_safe

logger = logging.getLogger(__name__)

# 视频代理下载目录（相对于项目根）
_VIDEO_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "media")

# 通用超时
_DEFAULT_IMAGE_TIMEOUT = 90      # 图像生成超时（秒）
_DEFAULT_VIDEO_TIMEOUT = 300     # 视频生成超时（秒）
_DEFAULT_DOWNLOAD_TIMEOUT = 300  # 视频下载超时（秒）


# 视频代理下载最大大小（500MB）
_MAX_VIDEO_DOWNLOAD_SIZE = 500 * 1024 * 1024


def _ensure_video_cache_dir() -> str:
    """确保视频缓存目录存在，返回绝对路径。"""
    abs_dir = os.path.abspath(_VIDEO_CACHE_DIR)
    os.makedirs(abs_dir, exist_ok=True)
    return abs_dir


def _parse_api_error(status: int, body: str) -> str:
    """从 HTTP 错误响应中提取可读的错误信息。"""
    return f"媒体生成服务返回错误 (HTTP {status})"


class ImageGenHandler:
    """AI 图像生成处理器。

    支持:
    - 文生图: POST /images/generations (wan2.6-t2i)
    - 图生图: POST /images/edits (qwen-image-2.0, multipart)
    """

    @staticmethod
    def generate_image(
        prompt: str,
        model_name: str,
        api_base: str,
        api_key: str,
        size: str = "1024x1024",
        n: int = 1,
        timeout: int = _DEFAULT_IMAGE_TIMEOUT,
    ) -> Dict[str, Any]:
        """文生图。调用 POST {api_base}/images/generations。

        Returns:
            {"success": True, "urls": [...], "model": str, "prompt": str}
            {"success": False, "error": str}
        """
        url = api_base.rstrip("/") + "/images/generations"

        safe, reason, _ = validate_url_safe(url)
        if not safe:
            return {"success": False, "error": f"API Base URL 不安全: {reason}"}

        payload = json.dumps({
            "model": model_name,
            "prompt": prompt,
            "n": n,
            "size": size,
        }).encode("utf-8")

        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": "Bearer " + (api_key or ""),
        }

        try:
            resp = safe_http_request(url, method="POST", headers=headers, body=payload, timeout=timeout)
            body = resp.body.decode("utf-8")
            if resp.status >= 400:
                error_msg = _parse_api_error(resp.status, body)
                logger.warning(f"图像生成失败 (HTTP {resp.status}): {error_msg}")
                return {"success": False, "error": error_msg}
        except SafeHttpError as e:
            logger.warning(f"图像生成请求失败: {e}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"图像生成异常: {e}")
            return {"success": False, "error": str(e)}

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return {"success": False, "error": f"API 返回非 JSON: {body[:200]}"}

        if data.get("data") and isinstance(data["data"], list):
            urls = []
            for item in data["data"]:
                if isinstance(item, dict) and item.get("url"):
                    urls.append(item["url"])
            if urls:
                return {
                    "success": True,
                    "urls": urls,
                    "model": model_name,
                    "prompt": prompt,
                }

        error_msg = _parse_api_error(200, body)
        return {"success": False, "error": error_msg or "API 返回格式异常"}

    @staticmethod
    def edit_image(
        prompt: str,
        image_data: bytes,
        image_filename: str,
        model_name: str,
        api_base: str,
        api_key: str,
        size: str = "1024x1024",
        n: int = 1,
        timeout: int = _DEFAULT_IMAGE_TIMEOUT,
    ) -> Dict[str, Any]:
        """图生图。调用 POST {api_base}/images/edits (multipart/form-data)。

        Args:
            image_data: 图片文件的二进制内容。
            image_filename: 图片文件名。

        Returns:
            {"success": True, "urls": [...], "model": str, "prompt": str}
            {"success": False, "error": str}
        """
        url = api_base.rstrip("/") + "/images/edits"

        safe, reason, _ = validate_url_safe(url)
        if not safe:
            return {"success": False, "error": f"API Base URL 不安全: {reason}"}

        # 构建 multipart/form-data 体
        boundary = "----FinderOSBoundary" + uuid.uuid4().hex[:16]
        body = b""

        # 表单字段
        for field_name, field_value in [
            ("model", model_name),
            ("prompt", prompt),
            ("n", str(n)),
            ("size", size),
        ]:
            body += f"--{boundary}\r\n".encode("utf-8")
            body += f'Content-Disposition: form-data; name="{field_name}"\r\n\r\n'.encode("utf-8")
            body += field_value.encode("utf-8") + b"\r\n"

        # 图片文件
        body += f"--{boundary}\r\n".encode("utf-8")
        body += f'Content-Disposition: form-data; name="image"; filename="{image_filename}"\r\n'.encode("utf-8")
        body += b"Content-Type: image/png\r\n\r\n"
        body += image_data + b"\r\n"
        body += f"--{boundary}--\r\n".encode("utf-8")

        headers = {
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Authorization": "Bearer " + (api_key or ""),
        }

        try:
            resp = safe_http_request(url, method="POST", headers=headers, body=body, timeout=timeout)
            resp_body = resp.body.decode("utf-8")
            if resp.status >= 400:
                error_msg = _parse_api_error(resp.status, resp_body)
                logger.warning(f"图像编辑失败 (HTTP {resp.status}): {error_msg}")
                return {"success": False, "error": error_msg}
        except SafeHttpError as e:
            logger.warning(f"图像编辑请求失败: {e}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"图像编辑异常: {e}")
            return {"success": False, "error": str(e)}

        try:
            data = json.loads(resp_body)
        except json.JSONDecodeError:
            return {"success": False, "error": f"API 返回非 JSON: {resp_body[:200]}"}

        if data.get("data") and isinstance(data["data"], list):
            urls = []
            for item in data["data"]:
                if isinstance(item, dict) and item.get("url"):
                    urls.append(item["url"])
            if urls:
                return {
                    "success": True,
                    "urls": urls,
                    "model": model_name,
                    "prompt": prompt,
                }

        error_msg = _parse_api_error(200, resp_body)
        return {"success": False, "error": error_msg or "API 返回格式异常"}


class VideoGenHandler:
    """AI 视频生成处理器。

    支持:
    - 文生视频: POST /videos/generations (wan2.6-t2v)
    - 图生视频: POST /videos/generations (wan2.6-i2v, +image_url)

    视频生成后立即代理下载到本地 static/media/ 目录，
    因为 API 返回的 OSS 签名链接有时效。
    """

    @staticmethod
    def generate_video(
        prompt: str,
        model_name: str,
        api_base: str,
        api_key: str,
        image_url: Optional[str] = None,
        timeout: int = _DEFAULT_VIDEO_TIMEOUT,
    ) -> Dict[str, Any]:
        """生成视频并代理下载到本地。

        Returns:
            {"success": True, "local_url": "/static/media/xxx.mp4",
             "content_type": "video/mp4", "model": str, "prompt": str,
             "original_url": str}
            {"success": False, "error": str}
        """
        url = api_base.rstrip("/") + "/videos/generations"

        safe, reason, _ = validate_url_safe(url)
        if not safe:
            return {"success": False, "error": f"API Base URL 不安全: {reason}"}

        payload_dict: Dict[str, Any] = {
            "model": model_name,
            "prompt": prompt,
        }
        if image_url:
            payload_dict["image_url"] = image_url

        payload = json.dumps(payload_dict).encode("utf-8")
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": "Bearer " + (api_key or ""),
        }

        try:
            resp = safe_http_request(url, method="POST", headers=headers, body=payload, timeout=timeout)
            body = resp.body.decode("utf-8")
            if resp.status >= 400:
                error_msg = _parse_api_error(resp.status, body)
                logger.warning(f"视频生成失败 (HTTP {resp.status}): {error_msg}")
                return {"success": False, "error": error_msg}
        except SafeHttpError as e:
            logger.warning(f"视频生成请求失败: {e}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"视频生成异常: {e}")
            return {"success": False, "error": str(e)}

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return {"success": False, "error": f"API 返回非 JSON: {body[:200]}"}

        if not (data.get("data") and isinstance(data["data"], list) and len(data["data"]) > 0):
            error_msg = _parse_api_error(200, body)
            return {"success": False, "error": error_msg or "API 未返回视频数据"}

        video_item = data["data"][0]
        remote_url = video_item.get("url", "")
        content_type = video_item.get("content_type", "video/mp4")

        if not remote_url:
            return {"success": False, "error": "API 返回的视频 URL 为空"}

        # 代理下载视频到本地
        cache_dir = _ensure_video_cache_dir()
        ext = ".mp4"
        local_filename = f"video_{uuid.uuid4().hex[:12]}{ext}"
        local_path = os.path.join(cache_dir, local_filename)

        # 代理下载前校验 URL 安全（防 SSRF）
        safe, reason, _ = validate_url_safe(remote_url)
        if not safe:
            return {
                "success": False,
                "error": f"视频下载 URL 不安全: {reason}",
                "original_url": remote_url,
            }

        try:
            logger.info(f"开始代理下载视频: {remote_url[:100]}...")
            dl_resp = safe_http_request(remote_url, method="GET", timeout=_DEFAULT_DOWNLOAD_TIMEOUT, max_bytes=_MAX_VIDEO_DOWNLOAD_SIZE)
            with open(local_path, "wb") as f:
                f.write(dl_resp.body)
            total = len(dl_resp.body)
            logger.info(f"视频下载完成: {local_path} ({total} bytes)")
        except Exception as e:
            logger.error(f"视频代理下载失败: {e}")
            # 清理不完整的文件
            if os.path.exists(local_path):
                try:
                    os.remove(local_path)
                except OSError:
                    pass
            return {
                "success": False,
                "error": f"视频生成成功但下载失败: {str(e)}",
                "original_url": remote_url,
            }

        local_url = f"/static/media/{local_filename}"

        return {
            "success": True,
            "local_url": local_url,
            "local_path": local_path,
            "content_type": content_type,
            "model": model_name,
            "prompt": prompt,
            "original_url": remote_url,
        }


def call_image_gen_in_thread(
    prompt: str,
    model_name: str,
    api_base: str,
    api_key: str,
    size: str = "1024x1024",
    n: int = 1,
) -> Dict[str, Any]:
    """在线程池中同步调用图像生成（供 async 层使用）。"""
    return ImageGenHandler.generate_image(
        prompt=prompt,
        model_name=model_name,
        api_base=api_base,
        api_key=api_key,
        size=size,
        n=n,
    )


def call_video_gen_in_thread(
    prompt: str,
    model_name: str,
    api_base: str,
    api_key: str,
    image_url: Optional[str] = None,
) -> Dict[str, Any]:
    """在线程池中同步调用视频生成（供 async 层使用）。"""
    return VideoGenHandler.generate_video(
        prompt=prompt,
        model_name=model_name,
        api_base=api_base,
        api_key=api_key,
        image_url=image_url,
    )
