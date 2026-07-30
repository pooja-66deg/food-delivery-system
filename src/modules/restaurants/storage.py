"""Local image storage for restaurant/menu images.

Files are written under ``settings.media_root`` and served at ``/media``. Swap
``save_image`` for a Cloud Storage / S3 upload later — the return value (a public
URL path) is the only contract callers depend on.
"""
import os
import uuid

from fastapi import UploadFile

from src.config import settings
from src.core.exceptions import ValidationException

_ALLOWED = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB


async def save_image(upload: UploadFile, subdir: str) -> str:
    """Validate and store an uploaded image; return its public URL path."""
    ext = _ALLOWED.get(upload.content_type or "")
    if ext is None:
        raise ValidationException("Unsupported image type. Use JPEG, PNG, or WebP.")

    data = await upload.read()
    if len(data) > _MAX_BYTES:
        raise ValidationException("Image is too large (max 5 MB).")

    folder = os.path.join(settings.media_root, subdir)
    os.makedirs(folder, exist_ok=True)
    name = f"{uuid.uuid4().hex}{ext}"
    with open(os.path.join(folder, name), "wb") as f:
        f.write(data)
    return f"/media/{subdir}/{name}"
