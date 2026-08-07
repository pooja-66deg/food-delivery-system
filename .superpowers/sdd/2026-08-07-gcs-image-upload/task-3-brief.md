# Task 3: Implement GCS Storage Function

**Files:**
- Create: `src/modules/restaurants/storage_gcs.py`

**Interfaces:**
- Consumes: `google.cloud.storage.Client`, `settings.gcs_bucket_name` (from config)
- Produces: 
  - `save_image_gcs(upload: UploadFile, subdir: str) -> str` — saves to GCS, returns public URL
  - Raises `ValidationException` on invalid input (same as local implementation)

**Steps:**

- [ ] **Step 1: Write failing test for GCS storage**

Open `tests/modules/restaurants/test_images.py` and add this test at the end:

```python
import pytest
from unittest.mock import MagicMock, patch
from fastapi import UploadFile
from io import BytesIO
from src.core.exceptions import ValidationException

# Test GCS storage (mocked)
@patch("src.modules.restaurants.storage_gcs.storage.Client")
async def test_save_image_gcs_valid_file(mock_client_class):
    # Mock the GCS client
    mock_bucket = MagicMock()
    mock_blob = MagicMock()
    mock_bucket.blob.return_value = mock_blob
    mock_blob.public_url = "https://storage.googleapis.com/test-bucket/restaurants/1/abc123.jpg"
    
    mock_client = MagicMock()
    mock_client.bucket.return_value = mock_bucket
    mock_client_class.return_value = mock_client
    
    # Create a mock UploadFile
    upload = UploadFile(
        file=BytesIO(b"fake image data"),
        filename="test.jpg",
        content_type="image/jpeg"
    )
    
    # Import here so the patch is active
    from src.modules.restaurants.storage_gcs import save_image_gcs
    
    # Call the function
    url = await save_image_gcs(upload, "restaurants/1")
    
    # Assert it returns a public URL
    assert url.startswith("https://storage.googleapis.com/test-bucket/")
    assert ".jpg" in url
    # Assert the client was called
    mock_client.bucket.assert_called_once_with("test-bucket")

@patch("src.modules.restaurants.storage_gcs.storage.Client")
async def test_save_image_gcs_invalid_type(mock_client_class):
    upload = UploadFile(
        file=BytesIO(b"not an image"),
        filename="test.txt",
        content_type="text/plain"
    )
    
    from src.modules.restaurants.storage_gcs import save_image_gcs
    
    with pytest.raises(ValidationException, match="Unsupported image type"):
        await save_image_gcs(upload, "restaurants/1")
```

Run the test to verify it fails:
```bash
pytest tests/modules/restaurants/test_images.py::test_save_image_gcs_valid_file -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'src.modules.restaurants.storage_gcs'"

- [ ] **Step 2: Create storage_gcs.py with save_image_gcs() function**

Create `src/modules/restaurants/storage_gcs.py`:

```python
"""Google Cloud Storage adapter for image uploads.

Used in production (ENVIRONMENT=production). Saves to a public GCS bucket
and returns public URLs. Local development uses storage.py (local disk).
"""
import uuid
from fastapi import UploadFile
from google.cloud import storage

from src.config import settings
from src.core.exceptions import ValidationException

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
```

- [ ] **Step 3: Run tests to verify they pass**

```bash
pytest tests/modules/restaurants/test_images.py::test_save_image_gcs_valid_file -v
pytest tests/modules/restaurants/test_images.py::test_save_image_gcs_invalid_type -v
```

Expected: Both tests PASS.

- [ ] **Step 4: Commit**

```bash
git add src/modules/restaurants/storage_gcs.py tests/modules/restaurants/test_images.py
git commit -m "feat: add GCS storage implementation with tests"
```
