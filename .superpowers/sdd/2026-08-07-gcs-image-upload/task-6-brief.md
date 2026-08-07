# Task 6: Update GitHub Actions CI Workflow

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
