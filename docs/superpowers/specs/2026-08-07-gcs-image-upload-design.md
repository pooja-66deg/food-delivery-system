# GCS Image Upload Integration — Design Specification

**Date:** 2026-08-07  
**Feature:** Google Cloud Storage integration for restaurant and menu item image uploads  
**Status:** Design Phase

---

## 1. Overview

Replace local disk image storage with Google Cloud Storage for production deployments, while maintaining local file storage for development. The existing `storage.py` interface remains unchanged; the implementation swaps based on the deployment environment.

### Goals
- Enable production image uploads to GCS (public bucket, no auth needed for retrieval)
- Keep local development simple (disk + NGINX)
- Minimize code changes to existing upload endpoints
- Fail fast on GCS errors (no complex retry/queue logic)

---

## 2. Architecture

### 2.1 Storage Routing

**Local Development (`ENVIRONMENT=development`)**
- Save files to `media/{subdir}/{uuid}.{ext}` on disk
- Served by NGINX at `http://localhost:8000/media/...`
- No GCS dependencies or credentials needed
- Current implementation unchanged

**Production (`ENVIRONMENT=production`)**
- Save files to GCS bucket: `gs://{GCS_BUCKET_NAME}/{subdir}/{uuid}.{ext}`
- Return public URL: `https://storage.googleapis.com/{GCS_BUCKET_NAME}/{subdir}/{uuid}.{ext}`
- Uses Cloud Run's Workload Identity (implicit credentials)
- `GCS_BUCKET_NAME` from environment variable

### 2.2 Naming & Structure

Preserve current local naming conventions in GCS:
- Restaurant images: `gs://bucket/restaurants/{restaurant_id}/{uuid}.jpg`
- Menu item images: `gs://bucket/restaurants/{restaurant_id}/items/{uuid}.jpg`

This allows future bulk operations, cleanup, or migrations to be organized by restaurant.

### 2.3 Authentication

**Cloud Run (Production)**
- Workload Identity federation: Cloud Run service account has `roles/storage.objectCreator` on the GCS bucket
- No service account keys, secrets, or environment variables needed
- `google-cloud-storage` client auto-detects credentials via Application Default Credentials (ADC)

**Local Development**
- GCS is not used; skipped entirely via `ENVIRONMENT` check

**CI/Testing**
- Tests mock the GCS client; no real bucket access
- Integration tests can use a test bucket if needed (optional)

---

## 3. Implementation Details

### 3.1 New Files

**`src/modules/restaurants/storage_gcs.py`**
- `save_image_gcs(upload: UploadFile, subdir: str) -> str` — mirrors the current interface
- Instantiates `storage.Client()` (uses ADC for auth)
- Validates file type and size (reuse `_ALLOWED`, `_MAX_BYTES` from `storage.py`)
- Uploads to bucket, returns public URL
- Raises `ValidationException` on invalid input, generic exceptions propagate (fail fast)

### 3.2 Modified Files

**`src/modules/restaurants/storage.py`**
- Check `settings.environment` and route to local or GCS implementation
- If `environment == "production"`, import and call `save_image_gcs()`
- If `environment == "development"`, call local `save_image()` as today
- Both return the same URL format (string path)
- `ValidationException` raised in either path is caught by the same router endpoint

**`src/config.py`**
- Add `gcs_bucket_name: Optional[str] = None` setting
- Load from `GCS_BUCKET_NAME` environment variable
- No default; if unset in production, upload will fail (fast, obvious)

**`pyproject.toml`**
- Add `google-cloud-storage>=2.10.0` dependency

**`infra/gcp/cloudbuild.yaml`**
- Pass `GCS_BUCKET_NAME` as a substitution (e.g., `_GCS_BUCKET_NAME=food-delivery-images`)
- Cloud Run deploy step sets `--set-env-vars=...@GCS_BUCKET_NAME=${_GCS_BUCKET_NAME}`

### 3.3 No Changes Required

- `src/modules/restaurants/router.py` — endpoints unchanged, call `save_image()` as before
- Database schema — `image_url` column already stores arbitrary URL strings
- Frontend — consumes the same URL format
- NGINX config (local dev) — unchanged

---

## 4. Error Handling

### Upload Failures
- **Validation (invalid type/size):** `ValidationException` → 400 Bad Request (same as today)
- **GCS unavailable / permission denied:** Unhandled exception → 500 Internal Server Error
- **No retry logic:** User gets 500, can retry their request
- **No fallback:** If GCS fails, upload fails; we do not fall back to local disk in production

### Rationale
- GCS outages are rare; Cloud Run has network redundancy
- Fail-fast is honest and debuggable
- Queuing/retry can be added later if needed; not needed for MVP

---

## 5. Testing Strategy

### Unit Tests (`tests/modules/restaurants/test_images.py`)
- Mock `google.cloud.storage.Client`
- Test validation (file type, size) in isolation
- Test URL generation format
- No real bucket access

### Integration Tests (optional, behind `@pytest.mark.integration`)
- Spin up a test GCS bucket (or use a persistent test bucket)
- Full upload flow with real client
- Only runs when explicitly enabled (CI sets `pytest -m "not integration"` by default to skip)

### Local Development
- Tests use `ENVIRONMENT=development` (default in test env vars)
- Upload to real `media/` folder, no GCS involved
- `pytest` passes without GCS credentials

---

## 6. Configuration & Deployment

### Environment Variables (Production)

| Variable | Source | Example |
|----------|--------|---------|
| `ENVIRONMENT` | Cloud Run env | `production` |
| `GCS_BUCKET_NAME` | Cloud Build substitution | `food-delivery-images` |

### Cloud Build Setup (infra/gcp/cloudbuild.yaml)

```yaml
substitutions:
  _GCS_BUCKET_NAME: food-delivery-images  # or from variable

# In deploy-api step:
--set-env-vars=...@GCS_BUCKET_NAME=${_GCS_BUCKET_NAME}
```

### GCP IAM Setup (one-time)

Cloud Run service account needs:
- `roles/storage.objectCreator` on the GCS bucket (can write, cannot delete)
- Bucket should be public (no `roles/storage.objectViewer` required for public reads)

---

## 7. Future Extensions (Not in MVP)

- Image optimization (WebP, compression) — add a transform step in `storage_gcs.py`
- CDN caching — front GCS with Cloud CDN
- Signed URLs — track access, expiration
- Versioning / deletion — manage old images, cost optimization

---

## 8. Success Criteria

✅ Restaurant and menu item images upload to GCS in production  
✅ Public URLs returned and stored in `image_url` column  
✅ Local dev continues to use disk + NGINX  
✅ No changes to router endpoints  
✅ Tests pass (mock GCS, real local storage)  
✅ Fail-fast on GCS errors  

---

## Appendix: Code Structure Reference

```
src/modules/restaurants/
├── storage.py           (router: choose local vs GCS)
├── storage_gcs.py       (new: GCS implementation)
├── router.py            (unchanged: calls save_image())
└── models.py            (unchanged)

tests/modules/restaurants/
└── test_images.py       (updated: mock GCS client)

src/config.py            (add: gcs_bucket_name setting)
pyproject.toml           (add: google-cloud-storage)
infra/gcp/cloudbuild.yaml (add: _GCS_BUCKET_NAME substitution)
```
