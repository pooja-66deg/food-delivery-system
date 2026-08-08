"""Google Cloud Storage adapter for image uploads.

Used in production (ENVIRONMENT=production). Saves to a public GCS bucket
and returns public URLs. Local development uses storage.py (local disk).
"""
import uuid
from fastapi import UploadFile
from google.cloud import storage

from app.config import settings
from shared.errors import ValidationException

_ALLOWED = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB


async def save_image_gcs(upload: UploadFile, subdir: str) -> str:
    """Upload image to GCS bucket; return public URL.

    Args:
        upload: FastAPI UploadFile
        subdir: subdirectory path in bucket (e.g., "restaurants/1")

    Returns:
        Public GCS URL (https://storage.googleapis.com/bucket/...)

    Raises:
        ValidationException: Invalid file type or size
    """
    # Validate file type
    ext = _ALLOWED.get(upload.content_type or "")
    if ext is None:
        raise ValidationException("Unsupported image type. Use JPEG, PNG, or WebP.")

    # Validate file size
    data = await upload.read()
    if len(data) > _MAX_BYTES:
        raise ValidationException("Image is too large (max 5 MB).")

    # Get GCS client and bucket
    client = storage.Client()
    bucket = client.bucket(settings.gcs_bucket_name)

    # Generate unique filename
    name = f"{uuid.uuid4().hex}{ext}"
    blob_path = f"{subdir}/{name}"
    blob = bucket.blob(blob_path)

    # Upload to GCS
    blob.upload_from_string(data, content_type=upload.content_type)

    # Return public URL
    # GCS public URL format: https://storage.googleapis.com/BUCKET_NAME/BLOB_PATH
    return f"https://storage.googleapis.com/{settings.gcs_bucket_name}/{blob_path}"
