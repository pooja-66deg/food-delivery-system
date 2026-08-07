# Task 3: GCS Storage Implementation — Report

**Date:** 2026-08-07  
**Status:** DONE

## Summary

Successfully implemented the GCS storage adapter for image uploads. The implementation:
- Validates image file types (JPEG, PNG, WebP)
- Enforces a 5 MB file size limit
- Uploads files to Google Cloud Storage
- Returns public GCS URLs in the format `https://storage.googleapis.com/BUCKET_NAME/BLOB_PATH`
- Raises `ValidationException` on invalid inputs (matching local implementation behavior)

## Implementation Details

### Files Created
1. **`src/modules/restaurants/storage_gcs.py`** (54 lines)
   - Implements `save_image_gcs(upload: UploadFile, subdir: str) -> str`
   - Uses google-cloud-storage Client to manage uploads
   - Generates unique filenames using UUID
   - Returns public GCS URLs (no signed URLs, as specified)

### Files Modified
1. **`tests/modules/restaurants/test_images.py`** (added 42 lines)
   - `test_save_image_gcs_valid_file`: Verifies valid image upload returns correct public URL
   - `test_save_image_gcs_invalid_type`: Verifies invalid content types raise ValidationException

## Test Results

### Unit Tests (GCS specific)
```
test_save_image_gcs_valid_file ............................ PASSED
test_save_image_gcs_invalid_type ........................... PASSED
```

### Full Restaurant Module Tests
```
121 tests passed in 46.04s
Coverage: 64% (overall)
- storage_gcs.py: 95% coverage (21 statements, 1 missed: error path at line 38)
```

All existing restaurant tests continue to pass.

## Commit Information

**Recommended commit message:**
```
feat: add GCS storage implementation with tests
```

**Files to stage:**
- `src/modules/restaurants/storage_gcs.py` (new file)
- `tests/modules/restaurants/test_images.py` (modified — added GCS tests)

**Changes included:**
- GCS upload function with validation (content type, file size)
- UUID-based unique filenames
- Public URL generation without signing
- Comprehensive test coverage with mocked GCS client and settings
- Integration with existing `settings.gcs_bucket_name` from Task 2

## Key Design Decisions

1. **Async function**: `save_image_gcs` is async to match FastAPI's async patterns
2. **UUID filenames**: Prevents collisions and obfuscates original filenames
3. **No signing**: Public URLs match global constraint "Public GCS bucket URLs (no signed URLs)"
4. **Fail-fast on validation**: ValidationException raised immediately on invalid input
5. **Content-Type preservation**: Stored with upload to preserve image metadata

## Validation Checklist

- [x] Tests written before implementation (TDD)
- [x] Tests pass (100% of new tests, all existing tests)
- [x] File type validation (JPEG, PNG, WebP only)
- [x] File size validation (max 5 MB)
- [x] GCS integration via google-cloud-storage
- [x] Returns public GCS URLs
- [x] Raises ValidationException on errors
- [x] Uses settings.gcs_bucket_name from config
- [x] No image optimization (files saved as-is)
- [x] Code follows project conventions
- [x] Linting passes (flake8)

## Dependencies

From Task 1:
- `google-cloud-storage>=2.10.0` (available in environment)

From Task 2:
- `settings.gcs_bucket_name: Optional[str]` (available from src.config)

## Notes for Integration

- The function expects `settings.gcs_bucket_name` to be set (typically from `GCS_BUCKET_NAME` env var)
- Error handling is fail-fast: GCS client errors will propagate as exceptions
- In production (ENVIRONMENT=production), this should replace or be used alongside the local storage adapter
- The function reads the entire upload into memory before validation — suitable for images up to 5 MB
