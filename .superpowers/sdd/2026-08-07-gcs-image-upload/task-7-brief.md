# Task 7: Integration Test with Local Dev

**Files:**
- Verify: `tests/modules/restaurants/test_images.py` (already modified in prior tasks)

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
pytest tests/ -v --tb=short 2>&1 | head -100
```

Expected: Tests PASS. If any fail, investigate and fix.

- [ ] **Step 3: Verify no lint errors**

```bash
flake8 src/modules/restaurants/storage.py src/modules/restaurants/storage_gcs.py
```

Expected: No errors.

- [ ] **Step 4: Commit (if any changes made)**

If you made any fixes, commit them:

```bash
git add <files>
git commit -m "fix: <description>"
```

If no fixes needed, this step is skipped.
