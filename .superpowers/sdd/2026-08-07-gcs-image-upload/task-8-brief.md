# Task 8: Documentation & Final Checklist

**Files:**
- Modify: `infra/gcp/cloudbuild.yaml` (add comment)

**Steps:**

- [ ] **Step 1: Add a comment to cloudbuild.yaml explaining GCS bucket setup**

Open `infra/gcp/cloudbuild.yaml` and find the `_GCS_BUCKET_NAME` substitution. Add a comment above it:

```yaml
# GCS bucket for restaurant/menu images (public, Cloud Run service account needs objectCreator role)
_GCS_BUCKET_NAME: ""
```

- [ ] **Step 2: Run final test suite**

```bash
pytest -v --tb=short 2>&1 | head -50
flake8 src
```

Expected: All tests PASS, no lint errors.

- [ ] **Step 3: Commit**

```bash
git add infra/gcp/cloudbuild.yaml
git commit -m "docs: add GCS bucket setup notes to Cloud Build config"
```
