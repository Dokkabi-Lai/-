"""用户头像存储：生产环境用 Supabase Storage，本地回退到磁盘。"""
from __future__ import annotations

import mimetypes
from pathlib import Path
from uuid import uuid4

import httpx

from ..config import BASE_DIR, get_settings

MAX_AVATAR_BYTES = 3 * 1024 * 1024
ALLOWED_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}


def _extension(content_type: str, filename: str) -> str:
    normalized = (content_type or "").split(";")[0].strip().lower()
    if normalized in ALLOWED_TYPES:
        return ALLOWED_TYPES[normalized]
    guessed, _ = mimetypes.guess_type(filename or "")
    if guessed in ALLOWED_TYPES:
        return ALLOWED_TYPES[guessed]
    raise ValueError("仅支持 JPG、PNG、WebP 或 GIF 图片")


def _detected_extension(content: bytes) -> str:
    if content.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if content[:6] in {b"GIF87a", b"GIF89a"}:
        return ".gif"
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return ".webp"
    raise ValueError("文件内容不是受支持的图片")


def save_avatar(user_id: int, content: bytes, content_type: str, filename: str) -> str:
    if not content:
        raise ValueError("头像文件为空")
    if len(content) > MAX_AVATAR_BYTES:
        raise ValueError("头像不能超过 3MB")
    suffix = _extension(content_type, filename)
    if _detected_extension(content) != suffix:
        raise ValueError("图片格式与文件类型不一致")
    object_name = f"users/{user_id}/{uuid4().hex}{suffix}"
    settings = get_settings()
    storage = settings.storage

    if storage.supabase_url and storage.supabase_service_role_key:
        base = storage.supabase_url.rstrip("/")
        bucket = storage.supabase_bucket
        response = httpx.put(
            f"{base}/storage/v1/object/{bucket}/{object_name}",
            content=content,
            headers={
                "Authorization": f"Bearer {storage.supabase_service_role_key}",
                "apikey": storage.supabase_service_role_key,
                "Content-Type": content_type,
                "x-upsert": "true",
            },
            timeout=30,
        )
        if response.status_code >= 300:
            raise RuntimeError(f"头像上传失败：{response.text[:160]}")
        return f"{base}/storage/v1/object/public/{bucket}/{object_name}"

    avatar_dir = Path(storage.avatar_dir)
    if not avatar_dir.is_absolute():
        avatar_dir = BASE_DIR / avatar_dir
    target = avatar_dir / object_name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return f"/avatars/{object_name}"

