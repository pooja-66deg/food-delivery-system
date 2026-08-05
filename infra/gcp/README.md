# GCP Deployment

Target: **Cloud Run** (API + frontend), **Cloud SQL** (Postgres), **Memorystore**
(Redis), **Secret Manager** (secrets), **Artifact Registry** (images), **Cloud
Build** (CI/CD). Serverless-first for the MVP; the same images move to **GKE
Autopilot** later without code changes.

> Everything here creates config only. The `gcloud` commands must be run by you
> against your own GCP project (there is no cloud access from the dev harness).

## Prerequisites
- A GCP project with billing enabled.
- `gcloud` CLI installed and authenticated: `gcloud auth login && gcloud config set project PROJECT_ID`.

## One-time setup

```bash
export PROJECT_ID=your-project
export REGION=us-central1

# 1. Enable the APIs we use
gcloud services enable run.googleapis.com sqladmin.googleapis.com \
  redis.googleapis.com secretmanager.googleapis.com artifactregistry.googleapis.com \
  cloudbuild.googleapis.com vpcaccess.googleapis.com

# 2. Artifact Registry (Docker images)
gcloud artifacts repositories create food-delivery \
  --repository-format=docker --location=$REGION

# 3. Cloud SQL (PostgreSQL 15)
gcloud sql instances create food-db --database-version=POSTGRES_15 \
  --tier=db-f1-micro --region=$REGION
gcloud sql databases create fooddelivery --instance=food-db
gcloud sql users create fooduser --instance=food-db --password=STRONG_PASSWORD
# connection name looks like: PROJECT_ID:us-central1:food-db

# 4. Memorystore (Redis) + a Serverless VPC Access connector so Cloud Run can reach it
gcloud redis instances create food-cache --size=1 --region=$REGION
gcloud compute networks vpc-access connectors create food-connector \
  --region=$REGION --range=10.8.0.0/28

# 5. Secrets (Secret Manager)
#    DATABASE_URL uses the Cloud SQL unix socket; our engine adds +asyncpg automatically.
printf 'postgresql://fooduser:STRONG_PASSWORD@/fooddelivery?host=/cloudsql/%s:%s:food-db' \
  "$PROJECT_ID" "$REGION" | gcloud secrets create DATABASE_URL --data-file=-
printf 'redis://REDIS_PRIVATE_IP:6379/0' | gcloud secrets create REDIS_URL --data-file=-
printf 'a-long-random-production-secret' | gcloud secrets create JWT_SECRET_KEY --data-file=-
#    Server-side Google Maps key: Routes API (delivery ETAs) + Geocoding API
#    (resolving addresses to coordinates). Restrict it by API, not by referrer —
#    it is called from Cloud Run, not a browser. Keep it distinct from the
#    browser key passed to the frontend build (_MAPS_BROWSER_KEY).
printf 'AIza-your-SERVER-key' | gcloud secrets create GOOGLE_MAPS_API_KEY --data-file=-

# 6. Let Cloud Run's service account read the secrets (and connect to Cloud SQL)
PROJECT_NUM=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
SA="$PROJECT_NUM-compute@developer.gserviceaccount.com"
for s in DATABASE_URL REDIS_URL JWT_SECRET_KEY GOOGLE_MAPS_API_KEY; do
  gcloud secrets add-iam-policy-binding $s \
    --member="serviceAccount:$SA" --role=roles/secretmanager.secretAccessor
done
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SA" --role=roles/cloudsql.client
```

## Automatic deployment on merge to `main`

`.github/workflows/ci.yml` deploys on every push to `main` (which is what a merged
PR produces). Pull requests run tests only and never deploy.

The `deploy` job authenticates to GCP and then hands off to `cloudbuild.yaml` — it
does not reimplement the deploy. Cloud Build stays the single definition of how
this app ships; GitHub Actions is only the trigger.

Auth is **keyless**, via Workload Identity Federation. There is no service-account
JSON key in GitHub secrets — a long-lived key in CI is the credential most likely
to leak and the hardest to rotate.

### One-time setup (run these yourself — they touch your GCP project)

```bash
export PROJECT_ID=your-project
export GITHUB_REPO=pooja-66deg/food-delivery-system   # owner/repo
PROJECT_NUM=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')

gcloud services enable iamcredentials.googleapis.com sts.googleapis.com

# 1. A dedicated deploy service account. Separate from the Cloud Run runtime
#    account: this one starts builds, that one serves traffic.
gcloud iam service-accounts create github-deployer \
  --display-name="GitHub Actions deployer"
DEPLOYER="github-deployer@$PROJECT_ID.iam.gserviceaccount.com"

# 2. What it may do: submit builds, and let Cloud Build act for it.
for role in roles/cloudbuild.builds.editor roles/storage.admin \
            roles/artifactregistry.writer roles/run.admin \
            roles/iam.serviceAccountUser roles/serviceusage.serviceUsageConsumer; do
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$DEPLOYER" --role="$role" --condition=None
done

# 3. Workload Identity pool + an OIDC provider that trusts GitHub.
gcloud iam workload-identity-pools create github \
  --location=global --display-name="GitHub Actions"

gcloud iam workload-identity-pools providers create-oidc github-oidc \
  --location=global --workload-identity-pool=github \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository=='${GITHUB_REPO}'"
```

> The `--attribute-condition` is the security boundary, not a nicety. Without it
> **any** GitHub repository on the internet could mint tokens for this provider and
> deploy to your project. Scope it to your repo.

```bash
# 4. Let only this repository impersonate the deployer.
gcloud iam service-accounts add-iam-policy-binding "$DEPLOYER" \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/$PROJECT_NUM/locations/global/workloadIdentityPools/github/attribute.repository/$GITHUB_REPO"

# 5. Print the provider resource name for the GitHub secret below.
echo "GCP_WIF_PROVIDER=projects/$PROJECT_NUM/locations/global/workloadIdentityPools/github/providers/github-oidc"
echo "GCP_DEPLOY_SERVICE_ACCOUNT=$DEPLOYER"
```

### GitHub configuration

Under **Settings → Secrets and variables → Actions**:

**Secrets** (2):

| Secret | Value |
|--------|-------|
| `GCP_WIF_PROVIDER` | the `projects/.../providers/github-oidc` string printed above |
| `GCP_DEPLOY_SERVICE_ACCOUNT` | `github-deployer@PROJECT_ID.iam.gserviceaccount.com` |

**Variables** (not secrets — they appear in build logs anyway):

| Variable | Required | Value |
|----------|:--------:|-------|
| `GCP_PROJECT_ID` | yes | your project id |
| `GCP_CLOUDSQL_INSTANCE` | yes | `PROJECT:REGION:food-db` |
| `GCP_VPC_CONNECTOR` | yes | `food-connector` |
| `GCP_API_URL` | yes | public API URL (see bootstrap below) |
| `GCP_FE_URL` | yes | public frontend URL — sets `CORS_ORIGINS` **and** `FRONTEND_BASE_URL` |
| `GCP_REGION` | no | defaults to `us-central1` |
| `GCP_AR_REPO` | no | defaults to `food-delivery` |
| `GCP_MAPS_BROWSER_KEY` | no | referrer-restricted browser key; unset means ETA-as-text, no map |

The `deploy` job fails fast with a named list if any required variable is unset,
because a Cloud Run deploy with an empty Cloud SQL instance or API URL *succeeds*
and then serves a broken app.

### CI-only variables (all optional)

The backend test job's throwaway credentials also come from variables, so they are
defined in one place rather than repeated across the service container and the
connection URL. **Every one has a literal fallback**, so leaving them unset is a
supported state — CI is green on a fresh clone or a fork with no configuration at all.

| Variable | Falls back to |
|----------|---------------|
| `CI_POSTGRES_USER` | `fooduser` |
| `CI_POSTGRES_PASSWORD` | `foodpass` |
| `CI_POSTGRES_DB` | `fooddelivery` |
| `CI_JWT_SECRET_KEY` | `ci-secret-key` |

These are **variables, not secrets, deliberately**. The Postgres container exists only
for the life of the job and is reachable only on `localhost`; the JWT key signs tokens
only within the test run. Making them secrets would mask them in logs and turn a
connection error into an undiagnosable one.

### The first-deploy bootstrap

`GCP_API_URL` and `GCP_FE_URL` are chicken-and-egg: Cloud Run assigns the URLs, but
the frontend bundle needs the API URL at build time and the API needs the frontend
URL for CORS. So the first deploy is a two-pass affair:

1. Run the manual `gcloud builds submit` below once to create both services.
2. Read the two URLs (commands at the end of this file) and set `GCP_API_URL` and
   `GCP_FE_URL` as repository variables.
3. Every merge after that deploys correctly and unattended.

Mapping custom domains instead makes the URLs stable and skips the two-pass step.

### Rollback

Images are tagged with the commit sha, so a rollback is a redeploy of an older tag:

```bash
gcloud run deploy food-api --region=$REGION \
  --image=$REGION-docker.pkg.dev/$PROJECT_ID/food-delivery/api:<old-sha>
```

Or shift traffic without redeploying: `gcloud run services update-traffic food-api
--region=$REGION --to-revisions=<older-revision>=100`.

---

## Deploy manually

Still supported, and needed once for the bootstrap above.

```bash
# First pass: deploy so the API gets a URL. Then re-run with _API_URL set so the
# frontend is built pointing at it (or use a custom domain and set it once).
gcloud builds submit --config infra/gcp/cloudbuild.yaml --substitutions=\
_REGION=$REGION,\
_AR_REPO=food-delivery,\
_CLOUDSQL_INSTANCE=$PROJECT_ID:$REGION:food-db,\
_VPC_CONNECTOR=food-connector,\
_API_URL=https://food-api-REPLACE.run.app,\
_FE_URL=https://food-frontend-REPLACE.run.app,\
_MAPS_BROWSER_KEY=AIza-your-BROWSER-key,\
_TAG=$(git rev-parse --short HEAD)
```

On PowerShell (Windows), `export` and `\` line continuations do not work. Use one
line, and note that `$PROJECT_ID:` must be written `$($env:PROJECT_ID):` or
PowerShell parses the colon as a drive qualifier:

```powershell
$tag = git rev-parse --short HEAD
gcloud builds submit --config infra/gcp/cloudbuild.yaml --substitutions="_REGION=us-central1,_AR_REPO=food-delivery,_CLOUDSQL_INSTANCE=food-project-poc:us-central1:food-db,_VPC_CONNECTOR=food-connector,_API_URL=https://food-api-REPLACE.run.app,_TAG=$tag"
```

`_MAPS_BROWSER_KEY` appears in the build logs and in the shipped JS bundle, which
is fine for a referrer-restricted Maps-JavaScript-only key and not fine for the
server key. If you have only one key, leave this empty: tracking still works and
shows the ETA as text instead of a map.

Get the service URLs:

```bash
gcloud run services describe food-api      --region=$REGION --format='value(status.url)'
gcloud run services describe food-frontend --region=$REGION --format='value(status.url)'
```

## Notes
- **Kafka**: not required for the MVP path (the app tolerates it being absent). When
  M5 needs it, use **Managed Service for Apache Kafka** (keeps the Kafka API) or
  **Pub/Sub**, and point `KAFKA_BROKERS` at it.
- **CORS**: the API uses an explicit allowlist from `CORS_ORIGINS`, which the deploy
  sets from `_FE_URL`. It is not `*`, and it must not be — the API sends credentials.
- **Scale to GKE** later: the same Artifact Registry images deploy to GKE Autopilot;
  add Anthos Service Mesh when the monolith is split.
