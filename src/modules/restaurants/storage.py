"""Image storage abstraction — routes to local or GCS based on environment.

Local development (ENVIRONMENT=development): save to media_root, served by NGINX.
Production (ENVIRONMENT=production): upload to GCS, return public URL.

Both return the same URL format; callers don't know which backend is in use.
"""
import os
import uuid

from fastapi import UploadFile

from src.config import settings
from src.core.exceptions import ValidationException

_ALLOWED = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB


async def save_image(upload: UploadFile, subdir: str) -> str:
    """Validate and store an uploaded image; return its public URL path.

    Routes to local disk (development) or GCS (production) based on ENVIRONMENT.
    """
    if settings.environment == "production":
        from src.modules.restaurants.storage_gcs import save_image_gcs
        return await save_image_gcs(upload, subdir)
    else:
        # Local development: save to disk
        return await _save_image_local(upload, subdir)


async def _save_image_local(upload: UploadFile, subdir: str) -> str:
    """Save image to local disk; return /media URL."""
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
