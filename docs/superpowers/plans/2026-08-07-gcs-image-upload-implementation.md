# GCS Image Upload Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate image uploads from local disk to Google Cloud Storage in production, while keeping local development unchanged.

**Architecture:** Environment-based routing in `storage.py` — checks `ENVIRONMENT` and dispatches to either local file storage (dev) or GCS (prod). Both implementations share the same interface and return URL strings. GCS uses Cloud Run's Workload Identity for implicit authentication; no credentials stored. All errors fail fast.

**Tech Stack:** 
- `google-cloud-storage>=2.10.0` (GCS client)
- `pydantic-settings` (already in use for config)
- `pytest-mock` (already in use for test mocking)

## Global Constraints

- Python 3.11–3.13
- No image optimization; save files as-is
- Public GCS bucket URLs (no signed URLs)
- Fail-fast on GCS errors (no retry/queue logic)
- Environment variable: `ENVIRONMENT` determines local vs GCS
- GCS bucket name from `GCS_BUCKET_NAME` environment variable

---

## Task 1: Add google-cloud-storage Dependency

**Files:**
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: `google-cloud-storage>=2.10.0` available in the Python environment

**Steps:**

- [ ] **Step 1: Add dependency to pyproject.toml**

Open `pyproject.toml` and find the `dependencies` list. Add `google-cloud-storage>=2.10.0` in alphabetical order (should go after `google-auth` if present, or in the general alphabetical sequence).

Current state (partial):
```toml
dependencies = [
    "fastapi>=0.104",
    "pydantic>=2.0",
    "sqlalchemy>=2.0",
    # ... add here
]
```

After adding:
```toml
dependencies = [
    "fastapi>=0.104",
    "google-cloud-storage>=2.10.0",
    "pydantic>=2.0",
    "sqlalchemy>=2.0",
    # ...
]
```

- [ ] **Step 2: Run uv lock to update lock file**

```bash
cd d:\Food\food-delivery-system
uv lock
```

Expected: `uv.lock` is updated with `google-cloud-storage` and its transitive dependencies.

- [ ] **Step 3: Verify import works**

```bash
python -c "from google.cloud import storage; print(storage.__version__)"
```

Expected: Version number prints without error.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "feat: add google-cloud-storage dependency"
```

---

## Task 2: Add GCS Configuration

**Files:**
- Modify: `src/config.py`

**Interfaces:**
- Produces: 
  - `settings.gcs_bucket_name: Optional[str]` (loaded from `GCS_BUCKET_NAME` env var)
  - Default is `None`; required in production, ignored in development

**Steps:**

- [ ] **Step 1: Add gcs_bucket_name field to Settings class**

Open `src/config.py` and locate the `Settings` class. Find the line `media_root: str = "media"` (around line 58). Add the GCS setting right after it:

```python
# Media (uploaded images)
media_root: str = "media"

# Google Cloud Storage (production only)
gcs_bucket_name: Optional[str] = None
```

- [ ] **Step 2: Verify config loads from environment**

Create a temporary test file `test_config_gcs.py`:

```python
import os
os.environ["GCS_BUCKET_NAME"] = "test-bucket"
from src.config import settings
assert settings.gcs_bucket_name == "test-bucket"
print("✓ Config loads GCS_BUCKET_NAME correctly")
```

Run it:
```bash
python test_config_gcs.py
```

Expected: "✓ Config loads GCS_BUCKET_NAME correctly" prints.

- [ ] **Step 3: Clean up test file**

```bash
rm test_config_gcs.py
```

- [ ] **Step 4: Commit**

```bash
git add src/config.py
git commit -m "feat: add gcs_bucket_name configuration"
```

---

## Task 3: Implement GCS Storage Function

**Files:**
- Create: `src/modules/restaurants/storage_gcs.py`

**Interfaces:**
- Consumes: `google.cloud.storage.Client`, `settings.gcs_bucket_name` (from config)
- Produces: 
  - `save_image_gcs(upload: UploadFile, subdir: str) -> str` — saves to GCS, returns public URL
  - Raises `ValidationException` on invalid input (same as local implementation)

**Steps:**

- [ ] **Step 1: Write failing test for GCS storage**

Open `tests/modules/restaurants/test_images.py` and add this test at the end of the file (before running any other tests):

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

---

## Task 4: Update storage.py to Route Based on Environment

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

Add this test to `tests/modules/restaurants/test_images.py`:

```python
@pytest.mark.asyncio
async def test_save_image_routes_to_local_in_dev(monkeypatch):
    """In development environment, save_image routes to local storage."""
    # Mock the config to return development environment
    monkeypatch.setattr("src.modules.restaurants.storage.settings.environment", "development")
    
    from src.modules.restaurants.storage import save_image
    
    # Create a real test image file
    upload = UploadFile(
        file=BytesIO(b"fake jpeg data"),
        filename="test.jpg",
        content_type="image/jpeg"
    )
    
    # Call save_image (should route to local)
    url = await save_image(upload, "test")
    
    # Should return a /media URL
    assert url.startswith("/media/test/")
    assert url.endswith(".jpg")

@pytest.mark.asyncio
@patch("src.modules.restaurants.storage_gcs.storage.Client")
async def test_save_image_routes_to_gcs_in_prod(mock_client_class, monkeypatch):
    """In production environment, save_image routes to GCS."""
    # Mock the config to return production environment
    monkeypatch.setattr("src.modules.restaurants.storage.settings.environment", "production")
    
    # Mock GCS
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
    
    # Call save_image (should route to GCS)
    url = await save_image(upload, "restaurants/1")
    
    # Should return a GCS URL
    assert url.startswith("https://storage.googleapis.com/")
```

Run the tests:
```bash
pytest tests/modules/restaurants/test_images.py::test_save_image_routes_to_local_in_dev -v
pytest tests/modules/restaurants/test_images.py::test_save_image_routes_to_gcs_in_prod -v
```

Expected: Both tests PASS.

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

---

## Task 5: Update Cloud Build Configuration

**Files:**
- Modify: `infra/gcp/cloudbuild.yaml`

**Interfaces:**
- Produces: `_GCS_BUCKET_NAME` substitution available in deploy step

**Steps:**

- [ ] **Step 1: Add _GCS_BUCKET_NAME substitution**

Open `infra/gcp/cloudbuild.yaml`. Find the `substitutions:` section (around line 13) and add:

```yaml
substitutions:
  _REGION: us-central1
  _AR_REPO: food-delivery
  _API_SERVICE: food-api
  _FE_SERVICE: food-frontend
  _CLOUDSQL_INSTANCE: ""
  _VPC_CONNECTOR: ""
  _GCS_BUCKET_NAME: ""          # Add this line
  _API_URL: ""
  _FE_URL: ""
  # ... rest of substitutions
```

- [ ] **Step 2: Update deploy-api step to pass GCS_BUCKET_NAME env var**

In the `deploy-api` step (around line 115), find the `--set-env-vars` line and add `GCS_BUCKET_NAME`:

Before:
```yaml
- --set-env-vars=^@^ENVIRONMENT=production@KAFKA_BROKERS=disabled:9092@CORS_ORIGINS=${_FE_URL}@FRONTEND_BASE_URL=${_FE_URL}
```

After:
```yaml
- --set-env-vars=^@^ENVIRONMENT=production@KAFKA_BROKERS=disabled:9092@CORS_ORIGINS=${_FE_URL}@FRONTEND_BASE_URL=${_FE_URL}@GCS_BUCKET_NAME=${_GCS_BUCKET_NAME}
```

- [ ] **Step 3: Verify YAML syntax**

```bash
python -c "import yaml; yaml.safe_load(open('infra/gcp/cloudbuild.yaml'))" && echo "✓ YAML is valid"
```

Expected: "✓ YAML is valid" prints.

- [ ] **Step 4: Commit**

```bash
git add infra/gcp/cloudbuild.yaml
git commit -m "feat: add GCS_BUCKET_NAME to Cloud Build substitutions"
```

---

## Task 6: Update GitHub Actions to Pass GCS Bucket

**Files:**
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Produces: `GCS_BUCKET_NAME` variable passed to Cloud Build

**Steps:**

- [ ] **Step 1: Update CI workflow to pass GCS bucket**

Open `.github/workflows/ci.yml`. Find the `Deploy` job's `gcloud builds submit` step (around line 128). Update the substitutions:

Before:
```bash
SUBS="_REGION=${{ vars.GCP_REGION || 'us-central1' }},_AR_REPO=${{ vars.GCP_AR_REPO || 'food-delivery' }},_CLOUDSQL_INSTANCE=${{ vars.GCP_CLOUDSQL_INSTANCE }},_VPC_CONNECTOR=${{ vars.GCP_VPC_CONNECTOR }},_API_URL=${{ vars.GCP_API_URL }},_FE_URL=${{ vars.GCP_FE_URL }},_MAPS_BROWSER_KEY=${{ vars.GCP_MAPS_BROWSER_KEY }},_STRIPE_PUBLISHABLE_KEY=${{ vars.GCP_STRIPE_PUBLISHABLE_KEY }},_TAG=${{ github.sha }}"
```

After:
```bash
SUBS="_REGION=${{ vars.GCP_REGION || 'us-central1' }},_AR_REPO=${{ vars.GCP_AR_REPO || 'food-delivery' }},_CLOUDSQL_INSTANCE=${{ vars.GCP_CLOUDSQL_INSTANCE }},_VPC_CONNECTOR=${{ vars.GCP_VPC_CONNECTOR }},_GCS_BUCKET_NAME=${{ vars.GCP_GCS_BUCKET_NAME }},_API_URL=${{ vars.GCP_API_URL }},_FE_URL=${{ vars.GCP_FE_URL }},_MAPS_BROWSER_KEY=${{ vars.GCP_MAPS_BROWSER_KEY }},_STRIPE_PUBLISHABLE_KEY=${{ vars.GCP_STRIPE_PUBLISHABLE_KEY }},_TAG=${{ github.sha }}"
```

Note: This assumes a GitHub Actions variable `GCP_GCS_BUCKET_NAME` is configured in the repo settings. If not, it will fail and the user will need to set it in their GitHub repo.

- [ ] **Step 2: Verify YAML syntax**

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))" && echo "✓ YAML is valid"
```

Expected: "✓ YAML is valid" prints.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "feat: add GCS_BUCKET_NAME to CI workflow substitutions"
```

---

## Task 7: Integration Test with Local Dev

**Files:**
- Modify: `tests/modules/restaurants/test_images.py` (already modified)

**Interfaces:**
- Consumes: Local image storage (from storage.py)
- Produces: Verified that local dev flow works end-to-end

**Steps:**

- [ ] **Step 1: Run full image test suite**

```bash
pytest tests/modules/restaurants/test_images.py -v
```

Expected: All tests PASS (no GCS used, all mocked or local disk).

- [ ] **Step 2: Run full backend test suite**

```bash
pytest tests/ -v --tb=short
```

Expected: All tests PASS. If any fail, investigate and fix.

- [ ] **Step 3: Verify local NGINX can serve uploaded images**

Upload a test image via the API (requires a running Docker Compose environment):

```bash
# Start the environment
docker compose -f infra/compose/docker-compose.yml up --build &

# Wait for API to be ready (takes ~10s)
sleep 10

# Create a restaurant (you'll need auth tokens — use the test fixtures)
# For now, just verify the endpoint exists
curl http://localhost:8000/docs

# If docs page loads, the API is up
```

Expected: API is running and healthy.

- [ ] **Step 4: Commit**

```bash
git add tests/modules/restaurants/test_images.py
git commit -m "test: verify local and GCS storage paths with end-to-end tests"
```

---

## Task 8: Documentation & Final Checklist

**Files:**
- Modify: `docs/architecture-overview.md` (optional, for reference)

**Steps:**

- [ ] **Step 1: Add a comment to storage.py explaining the routing**

The file already has a good docstring, so this is just verification. Check that `storage.py` has a clear module-level docstring explaining the environment routing.

- [ ] **Step 2: Document the GCS bucket setup requirement**

Create a note or add to `infra/gcp/README.md` (if it exists) explaining:
- GCS bucket must be public (bucket policy allows public read)
- Cloud Run service account needs `roles/storage.objectCreator` on the bucket
- Environment variable `GCS_BUCKET_NAME` must be set in Cloud Run deploy

For now, just verify the comment in `infra/gcp/cloudbuild.yaml` is clear:

Open `infra/gcp/cloudbuild.yaml` and find the `_GCS_BUCKET_NAME` substitution. Add a comment above it:

```yaml
# GCS bucket for restaurant/menu images (public, Cloud Run service account needs objectCreator role)
_GCS_BUCKET_NAME: ""
```

- [ ] **Step 3: Run final test suite**

```bash
pytest -v --tb=short
flake8 src
```

Expected: All tests PASS, no lint errors.

- [ ] **Step 4: Final commit**

```bash
git add infra/gcp/cloudbuild.yaml
git commit -m "docs: add GCS bucket setup notes to Cloud Build config"
```

---

## Summary of Changes

✅ **Dependency:** Added `google-cloud-storage>=2.10.0`  
✅ **Config:** Added `gcs_bucket_name` setting  
✅ **GCS Implementation:** Created `storage_gcs.py` with `save_image_gcs()`  
✅ **Routing:** Updated `storage.py` to dispatch based on `ENVIRONMENT`  
✅ **Cloud Build:** Added `_GCS_BUCKET_NAME` substitution  
✅ **CI:** Updated GitHub Actions to pass bucket name  
✅ **Tests:** Added tests for both local and GCS paths  

**Local development:** Unchanged (still uses disk + NGINX)  
**Production:** Images go to GCS via Workload Identity  
**Failures:** Fail-fast (no retry/fallback logic)

---
