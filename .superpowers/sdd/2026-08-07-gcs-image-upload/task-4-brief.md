# Task 4: Update storage.py to Route Based on Environment

**Files:**
- Modify: `src/modules/restaurants/storage.py`

**Interfaces:**
- Consumes: 
  - `settings.environment` (from config)
  - `save_image_gcs()` (from storage_gcs.py)
- Produces:
  - `save_image(upload: UploadFile, subdir: str) -> str` — routes to local or GCS

**Steps:**

- [ ] **Step 1: Update storage.py to add routing logic**

Open `src/modules/restaurants/storage.py` and replace the entire file with:

```python
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
```

- [ ] **Step 2: Write test for routing logic**

Add these tests to `tests/modules/restaurants/test_images.py`:

```python
@pytest.mark.asyncio
async def test_save_image_routes_to_local_in_dev(monkeypatch):
    """In development environment, save_image routes to local storage."""
    monkeypatch.setattr("src.modules.restaurants.storage.settings.environment", "development")
    
    from src.modules.restaurants.storage import save_image
    
    upload = UploadFile(
        file=BytesIO(b"fake jpeg data"),
        filename="test.jpg",
        content_type="image/jpeg"
    )
    
    url = await save_image(upload, "test")
    
    # Should return a /media URL
    assert url.startswith("/media/test/")
    assert url.endswith(".jpg")

@pytest.mark.asyncio
@patch("src.modules.restaurants.storage_gcs.storage.Client")
async def test_save_image_routes_to_gcs_in_prod(mock_client_class, monkeypatch):
    """In production environment, save_image routes to GCS."""
    monkeypatch.setattr("src.modules.restaurants.storage.settings.environment", "production")
    
    mock_bucket = MagicMock()
    mock_blob = MagicMock()
    mock_bucket.blob.return_value = mock_blob
    mock_blob.public_url = "https://storage.googleapis.com/bucket/test/abc.jpg"
    mock_client = MagicMock()
    mock_client.bucket.return_value = mock_bucket
    mock_client_class.return_value = mock_client
    
    from src.modules.restaurants.storage import save_image
    
    upload = UploadFile(
        file=BytesIO(b"fake jpeg data"),
        filename="test.jpg",
        content_type="image/jpeg"
    )
    
    url = await save_image(upload, "restaurants/1")
    
    # Should return a GCS URL
    assert url.startswith("https://storage.googleapis.com/")
```

- [ ] **Step 3: Run full test suite to ensure nothing broke**

```bash
pytest tests/modules/restaurants/test_images.py -v
```

Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add src/modules/restaurants/storage.py tests/modules/restaurants/test_images.py
git commit -m "feat: add environment-based routing to storage (local vs GCS)"
```
