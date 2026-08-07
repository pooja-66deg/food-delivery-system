# Task 5: Update Cloud Build Configuration

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
