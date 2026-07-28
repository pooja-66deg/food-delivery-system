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

# 6. Let Cloud Run's service account read the secrets (and connect to Cloud SQL)
PROJECT_NUM=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
SA="$PROJECT_NUM-compute@developer.gserviceaccount.com"
for s in DATABASE_URL REDIS_URL JWT_SECRET_KEY; do
  gcloud secrets add-iam-policy-binding $s \
    --member="serviceAccount:$SA" --role=roles/secretmanager.secretAccessor
done
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SA" --role=roles/cloudsql.client
```

## Deploy

```bash
# First pass: deploy so the API gets a URL. Then re-run with _API_URL set so the
# frontend is built pointing at it (or use a custom domain and set it once).
gcloud builds submit --config deploy/gcp/cloudbuild.yaml --substitutions=\
_REGION=$REGION,\
_AR_REPO=food-delivery,\
_CLOUDSQL_INSTANCE=$PROJECT_ID:$REGION:food-db,\
_VPC_CONNECTOR=food-connector,\
_API_URL=https://food-api-REPLACE.run.app
```

Get the service URLs:

```bash
gcloud run services describe food-api      --region=$REGION --format='value(status.url)'
gcloud run services describe food-frontend --region=$REGION --format='value(status.url)'
```

## Notes
- **Kafka**: not required for the MVP path (the app tolerates it being absent). When
  M5 needs it, use **Managed Service for Apache Kafka** (keeps the Kafka API) or
  **Pub/Sub**, and point `KAFKA_BROKERS` at it.
- **CORS**: the API currently allows all origins (fine for MVP). For production,
  restrict it to the frontend's URL in `src/main.py`.
- **Scale to GKE** later: the same Artifact Registry images deploy to GKE Autopilot;
  add Anthos Service Mesh when the monolith is split.
