# GCP Deployment

Target: **Cloud Run** (seven services + gateway + frontend), **Cloud SQL**
(Postgres, one database per service), **Memorystore** (Redis), **Pub/Sub**
(events), **Secret Manager** (secrets), **Artifact Registry** (images), **Cloud
Build** (CI/CD).

Three choices here are worth understanding before you run anything.

**Pub/Sub, not managed Kafka.** GCP's managed Kafka charges for cluster capacity
whether you use it or not; Pub/Sub is per-message with no floor, which is the
right shape at this volume. Services do not know the difference — the transport
is behind one interface in `shared/messaging.py` — so the compose stack keeps
Kafka and a developer still needs no cloud credentials.

**One Cloud SQL instance, seven databases.** A foreign key still cannot cross
between them, which is the isolation that actually matters, at a fraction of
seven instances' cost. Being straight about the trade: they share a failure
domain and a connection limit. Splitting the busiest onto its own instance is the
next step when load justifies it, and it needs no code change.

**The gateway is the only public door.** Services deploy with
`--ingress=internal-and-cloud-load-balancing`, so none is reachable from the
internet even if its auth were misconfigured.

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

# 3. Cloud SQL (PostgreSQL 15). The per-service databases are created by the
#    build pipeline, so only the instance and the user are needed here.
#    db-f1-micro is fine for staging; seven services sharing it will want more.
gcloud sql instances create food-db --database-version=POSTGRES_15 \
  --tier=db-f1-micro --region=$REGION
gcloud sql users create fooduser --instance=food-db --password=STRONG_PASSWORD
# connection name looks like: PROJECT_ID:us-central1:food-db

# 3b. Pub/Sub. Topics and subscriptions are created by the pipeline too — see the
#     provision-pubsub step, which is the only place their names are written down
#     besides each service's KAFKA_TOPICS. Just enable the API.
gcloud services enable pubsub.googleapis.com

# 4. Memorystore (Redis) + a Serverless VPC Access connector so Cloud Run can reach it
gcloud redis instances create food-cache --size=1 --region=$REGION
gcloud compute networks vpc-access connectors create food-connector \
  --region=$REGION --range=10.8.0.0/28

# 5. Secrets (Secret Manager)
#    One DATABASE_URL per service, because each has its own database.
#
#    A script rather than a loop to paste: a `for` loop pasted into a terminal
#    line by line runs with an empty loop variable and cheerfully creates a
#    secret named `_DATABASE_URL`, which looks like it worked.
./infra/gcp/create-secrets.sh $PROJECT_ID $REGION
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
SECRETS="REDIS_URL JWT_SECRET_KEY GOOGLE_MAPS_API_KEY"
for svc in USERS RESTAURANTS ORDERS PAYMENTS DELIVERY NOTIFICATIONS ADMIN; do
  SECRETS="$SECRETS ${svc}_DATABASE_URL"
done
for s in $SECRETS; do
  gcloud secrets add-iam-policy-binding $s \
    --member="serviceAccount:$SA" --role=roles/secretmanager.secretAccessor
done
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SA" --role=roles/cloudsql.client
# Publishing and subscribing. Every service does both, so this is granted once
# at the project level rather than per topic.
for role in roles/pubsub.publisher roles/pubsub.subscriber; do
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SA" --role="$role"
done
# The gateway calls the services, which are deployed --no-allow-unauthenticated,
# so it needs permission to invoke them.
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SA" --role=roles/run.invoker
```

## The first deploy takes two passes

The gateway needs each service's Cloud Run URL, and the frontend needs the
gateway's — none of which exist until something has been deployed. So:

1. Run the pipeline with the URL substitutions empty. Everything deploys; the
   gateway 502s and the frontend has no API. That is expected.
2. Read the URLs off `gcloud run services list --region=$REGION`.
3. Run it again with `_USERS_URL`, `_RESTAURANTS_URL`, `_ORDERS_URL`,
   `_PAYMENTS_URL`, `_DELIVERY_URL`, `_NOTIFICATIONS_URL`, `_ADMIN_URL`,
   `_GATEWAY_URL` and `_FE_URL` filled in.

Note that `_GATEWAY_URL` is baked into the SPA bundle at build time, so changing
it needs a rebuild and not just a redeploy.

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
| `GCP_GATEWAY_URL` | after pass 1 | public gateway URL — baked into the SPA bundle |
| `GCP_FE_URL` | after pass 1 | public frontend URL — sets `CORS_ORIGINS` **and** `FRONTEND_BASE_URL` |
| `GCP_USERS_URL` … `GCP_ADMIN_URL` | after pass 1 | each service's Cloud Run URL, for the gateway to route to |
| `GCP_REGION` | no | defaults to `us-central1` |
| `GCP_AR_REPO` | no | defaults to `food-delivery` |
| `GCP_MAPS_BROWSER_KEY` | no | referrer-restricted browser key; unset means ETA-as-text, no map |
| `GCP_ADMIN_ALERT_EMAIL` | no | operations mailbox told when a restaurant registers and needs approval; unset means operators find pending venues in the admin console instead |

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

The gateway needs each service's URL and the frontend needs the gateway's, but
Cloud Run assigns those URLs — so the first deploy cannot have them:

1. Merge to `main` with the URL variables unset. Everything deploys; the gateway
   502s and the frontend has no API. That is expected, not a failure.
2. Read the URLs: `gcloud run services list --region=$REGION --format='value(metadata.name,status.url)'`
3. Set them as repository variables and deploy again. From then on it is unattended.

`GCP_GATEWAY_URL` is baked into the SPA bundle at build time, so changing it needs
a rebuild, not just a redeploy. Mapping custom domains makes the URLs stable and
skips this entirely.

### Rollback

Images are tagged with the commit sha, so a rollback is a redeploy of an older tag:

```bash
gcloud run deploy orders-service --region=$REGION \
  --image=$REGION-docker.pkg.dev/$PROJECT_ID/food-delivery/orders:<old-sha>
```

Or shift traffic without redeploying: `gcloud run services update-traffic
orders-service --region=$REGION --to-revisions=<older-revision>=100`.

A schema change is the exception: migrations run forward as a deploy step and are
not undone by redeploying an older image. Roll one back with the service's own
chain — `cd services/orders && alembic downgrade -1`.

---

## Deploy manually

Still supported, and needed once for the bootstrap above.

```bash
gcloud builds submit --config infra/gcp/cloudbuild.yaml --substitutions=\
_REGION=$REGION,\
_AR_REPO=food-delivery,\
_CLOUDSQL_INSTANCE=$PROJECT_ID:$REGION:food-db,\
_VPC_CONNECTOR=food-connector,\
_TAG=$(git rev-parse --short HEAD)
```

That is pass 1 — no URL substitutions, because nothing has them yet. Read them
back, then re-run with `_GATEWAY_URL`, `_FE_URL` and the seven `_*_URL` values
filled in:

```bash
gcloud run services list --region=$REGION --format='value(metadata.name,status.url)'
```

`_MAPS_BROWSER_KEY` and `_STRIPE_PUBLISHABLE_KEY` appear in the build logs and in
the shipped JS bundle. That is fine for a referrer-restricted Maps-JavaScript key
and a Stripe publishable key — neither can do anything on its own — and not fine
for the server key or `sk_`, which live in Secret Manager.

## Notes

- **Events** go through Pub/Sub here and Kafka in the compose stack. Neither is
  visible to a service — the transport is behind one interface in
  `shared/messaging.py` — so local development needs no cloud credentials.
- **CORS**: the users service uses an explicit allowlist from `CORS_ORIGINS`,
  set from `_FE_URL`. It is not `*`, and must not be: the API sends credentials.
  Cloud Run gives each service two hostnames and CORS matches by exact string, so
  `_FE_URL` should list both, comma-separated.
- **One Cloud SQL instance, seven databases.** A foreign key still cannot cross
  between them, which is the isolation that matters, at a fraction of seven
  instances' cost. They do share a failure domain; splitting the busiest onto its
  own instance is the next step when load justifies it, and needs no code change.
- **`min-instances=1` on every service is not a performance tweak.** Each runs a
  Pub/Sub subscriber in a background thread, and Cloud Run stops background work
  on an idle instance — scaled to zero, a service stops consuming and its
  read-models silently stop updating.
