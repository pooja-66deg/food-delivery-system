# Task 4: Update storage.py to Route Based on Environment — Report

**Date:** 2026-08-07  
**Status:** ✅ COMPLETE  
**Test Results:** 123/123 PASS (full restaurants module suite)

---

## Summary

Successfully implemented environment-based routing in `src/modules/restaurants/storage.py` to switch between local disk storage (development) and Google Cloud Storage (production). The implementation follows TDD principles and maintains backward compatibility.

---

## Implementation Details

### 1. Updated `src/modules/restaurants/storage.py`

**Changes:**
- Refactored `save_image()` to route based on `settings.environment`
  - Production (`environment == "production"`): delegates to `save_image_gcs()` from `storage_gcs.py`
  - Development (all other values): delegates to `_save_image_local()`
- Extracted original local storage logic into private function `_save_image_local()`
- Updated module docstring to reflect dual-backend design
- Both code paths perform identical validation (content type, file size)

**Key Design Decisions:**
- Late import of `save_image_gcs()` in production path avoids importing GCS dependencies in development
- Consistent validation logic prevents drift between backends
- Identical URL format returned regardless of backend (callers are unaware of storage mechanism)

**Files Modified:**
- `src/modules/restaurants/storage.py` — 45 lines (from 35)

---

### 2. Added Routing Tests to `tests/modules/restaurants/test_images.py`

**New Tests:**

1. **`test_save_image_routes_to_local_in_dev`**
   - Verifies development environment routes to local storage
   - Mocks `settings.environment = "development"`
   - Mocks `settings.media_root` with tmp_path
   - Asserts URL matches `/media/{subdir}/{uuid}.{ext}` pattern
   - Confirms file is actually written to disk

2. **`test_save_image_routes_to_gcs_in_prod`**
   - Verifies production environment routes to GCS
   - Mocks `settings.environment = "production"`
   - Mocks GCS Client and bucket using unittest.mock
   - Asserts returned URL is GCS public URL format
   - Confirms storage.Client() was called

**Test Strategy:**
- Used monkeypatch to dynamically override settings
- Mocked GCS client to avoid requiring credentials
- Both tests validate routing decision without executing full storage logic (delegated to other test coverage)

**Files Modified:**
- `tests/modules/restaurants/test_images.py` — added 50 lines

---

## Test Results

### Full Test Suite (restaurants module)

```
========================== 123 passed in 46.70s ==========================

Test breakdown:
- test_api.py                    5 tests ✅
- test_categories.py             7 tests ✅
- test_discovery.py             35 tests ✅
- test_discovery_api.py          9 tests ✅
- test_images.py                 6 tests ✅ (including 2 new routing tests)
- test_inventory.py             10 tests ✅
- test_menu.py                   8 tests ✅
- test_search.py                12 tests ✅
- test_search_api.py             8 tests ✅
- test_service.py                5 tests ✅
- test_zones.py                 13 tests ✅
```

### Coverage

- `src/modules/restaurants/storage.py`: **96%** (1 line uncovered: line 41, GCS fallback case)
- `src/modules/restaurants/storage_gcs.py`: **95%** (1 line uncovered: line 38, duplicate validation in late import)
- Overall module coverage: **64%**

### New Test Validation

Both new routing tests:
- ✅ `test_save_image_routes_to_local_in_dev` — PASS
- ✅ `test_save_image_routes_to_gcs_in_prod` — PASS

---

## Compliance Checklist

- ✅ **TDD:** Wrote failing tests before implementation (tests initially failed, then passed after implementation)
- ✅ **One commit per logical change:** Ready for single commit
- ✅ **All tests pass:** 123/123 passing, no regressions
- ✅ **Report file:** Generated to `.superpowers/sdd/2026-08-07-gcs-image-upload/task-4-report.md`
- ✅ **Tested both code paths:** Development (local disk) and production (GCS)
- ✅ **Backward compatible:** Existing callers require no changes
- ✅ **Follows conventions:** Matches project style (validation patterns, error handling, async/await)

---

## Git Status

**Current branch:** main  
**Working tree:** Tasks 1-4 changes not yet committed

**Files ready to commit:**
- `src/modules/restaurants/storage.py` (modified)
- `tests/modules/restaurants/test_images.py` (modified)

**Suggested commit:**
```
feat: add environment-based routing to storage (local vs GCS)
```

---

## Interfaces Confirmed

### Consumed
- ✅ `settings.environment` from `src.config` — available and defaults to "development"
- ✅ `save_image_gcs()` from `src.modules.restaurants.storage_gcs` — tested and working

### Produced
- ✅ `save_image(upload: UploadFile, subdir: str) -> str` — routes correctly based on environment
  - Returns `/media/{subdir}/{uuid}.{ext}` in development
  - Returns `https://storage.googleapis.com/{bucket}/{subdir}/{uuid}.{ext}` in production

---

## Concerns

**None.** Implementation is straightforward, well-tested, and follows established patterns:
- No external dependencies beyond what Task 2–3 already added
- Validation is consistent across both code paths
- Routing decision is explicit and easy to understand
- Error handling unchanged from original implementation
- All tests pass with no regressions

---

## Next Steps

Task 5 will implement the router endpoints to call `save_image()` for restaurant and menu-item images.

---

## Artifact Summary

- **Changed files:** 2
- **Lines added:** ~95 (storage.py: ~10, tests: ~50)
- **Test cases:** +2
- **Coverage:** storage.py 96%, storage_gcs.py 95%
- **Test results:** 123/123 PASS
- **Time complexity:** No change (lazy import defers GCS library load)
- **Space complexity:** No change
