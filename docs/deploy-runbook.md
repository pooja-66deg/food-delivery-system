# Deploy Runbook — follow top to bottom

One linear sequence from nothing to "merging to `main` deploys automatically".
Every command is copy-paste. Do the steps in order and do not skip one.

**Read this first:**

- **The first deploy will NOT produce a working app. That is expected.** Cloud Run
  assigns the public URLs, and the app needs to know them (the frontend needs the API's
  URL, the API needs the frontend's for CORS). So deploy #1 creates the services and
  hands you the URLs; you save them in GitHub; deploy #2 is the working one. Do not
  panic at step 9.
- Steps 1–8 run in **your terminal**. Steps 9–11 are **clicks in GitHub**. Steps 12–14
  are terminal again. Step 15 is the real test.
- If a `create` command says `ALREADY_EXISTS`, that resource is already there. Ignore it
  and continue.

---

## Step 0 — Before you start

```bash
gcloud --version   # if this fails, install the gcloud CLI first
gcloud auth login
```

Have your GCP **project id** ready and make sure **billing is enabled** on it.
Nothing below works without billing.

---

## Step 1 — Set your terminal variables

Everything after this reuses them. Replace `your-project-id` only.

```bash
export PROJECT_ID=your-project-id
export REGION=us-central1
export GITHUB_REPO=pooja-66deg/food-delivery-system

gcloud config set project $PROJECT_ID
export PROJECT_NUM=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')

echo "Project: $PROJECT_ID   Number: $PROJECT_NUM   Region: $REGION"
```

**Checkpoint:** the echo prints a real project number (a long digit string). If it is
empty, the project id is wrong — fix it before continuing.

> If you close your terminal at any point, re-run this whole step before resuming.

> **Keep `REGION` as `us-central1` unless you have a reason not to.** The deploy job
> assumes that region by default. If you change it here, you must also add a variable
> named `GCP_REGION` with your region in step 11 — otherwise GitHub will deploy to
> `us-central1` while your database lives somewhere else, and the API will fail to
> connect for reasons that are not obvious from the logs.

---

## Step 2 — Enable the APIs

```bash
gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  redis.googleapis.com \
  secretmanager.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  vpcaccess.googleapis.com \
  iamcredentials.googleapis.com \
  sts.googleapis.com
```

This takes a minute or two. Wait for it to finish.

---

## Step 3 — Create the infrastructure

> **Already have a Cloud SQL instance?** Do **Step 3a** below instead of the
> `gcloud sql ...` commands here, then come back for Artifact Registry, Redis and the
> VPC connector.

Cloud SQL takes ~10 minutes. Start it and let it run.

```bash
# Choose a database password now and keep it for step 4.
export DB_PASSWORD='ChangeMe-StrongPassword-123'

# Docker image registry
gcloud artifacts repositories create food-delivery \
  --repository-format=docker --location=$REGION

# PostgreSQL
gcloud sql instances create food-db \
  --database-version=POSTGRES_15 --tier=db-f1-micro --region=$REGION
gcloud sql databases create fooddelivery --instance=food-db
gcloud sql users create fooduser --instance=food-db --password="$DB_PASSWORD"

# Redis + the connector Cloud Run needs to reach it privately
gcloud redis instances create food-cache --size=1 --region=$REGION
gcloud compute networks vpc-access connectors create food-connector \
  --region=$REGION --range=10.8.0.0/28
```

**Checkpoint:**

```bash
gcloud sql instances describe food-db --format='value(state)'          # RUNNABLE
gcloud redis instances describe food-cache --region=$REGION --format='value(state)'  # READY
```

Both must report the value shown. If Cloud SQL says `PENDING_CREATE`, wait and re-run.

Now skip to step 4 — **step 3a is only for people reusing an existing instance.**

---

## Step 3a — Reusing an existing Cloud SQL instance

Only do this if you skipped creating `food-db` above.

### Find out what you have

```bash
gcloud sql instances list
```

Take the `NAME` from that output, then:

```bash
export SQL_INSTANCE=<name-from-above>

gcloud sql instances describe $SQL_INSTANCE \
  --format="table(name, connectionName, region, databaseVersion, state)"

gcloud sql databases list --instance=$SQL_INSTANCE
gcloud sql users list --instance=$SQL_INSTANCE
```

Check three things before continuing:

- `databaseVersion` starts with `POSTGRES`. This app does not run on MySQL.
- `state` is `RUNNABLE`.
- `region` — **if it is not `us-central1`**, go back to step 1, set
  `export REGION=<that region>`, and remember to add a `GCP_REGION` variable in step 11.
  Cloud Run and the database should live in the same region.

### Make sure the app has a database and a user

If `fooddelivery` is missing from the databases list, or you have no user you want to
reuse, create them. Both are additive and leave anything already on the instance alone.

```bash
gcloud sql databases create fooddelivery --instance=$SQL_INSTANCE
gcloud sql users create fooduser --instance=$SQL_INSTANCE --password='StrongPassword-123'
```

### The password

**A Cloud SQL password cannot be read back** — there is no command for it. If you do not
know the password for the user you intend to use, set a new one:

```bash
gcloud sql users set-password fooduser --instance=$SQL_INSTANCE --password='StrongPassword-123'
```

> ⚠️ If anything else connects to this instance with that user — another app, a
> colleague's local setup — resetting the password breaks it. If the instance is only
> for this POC, go ahead.

### Carry your values forward

Step 4 and step 8 below are written for an instance named `food-db`. Set these so they
work unchanged:

```bash
export DB_PASSWORD='StrongPassword-123'      # the password you just set
export SQL_CONNECTION=$(gcloud sql instances describe $SQL_INSTANCE --format='value(connectionName)')

echo "Connection name: $SQL_CONNECTION"      # project:region:instance
```

Then in **step 4**, use this instead of the first `DATABASE_URL` command:

```bash
printf 'postgresql://fooduser:%s@/fooddelivery?host=/cloudsql/%s' \
  "$DB_PASSWORD" "$SQL_CONNECTION" \
  | gcloud secrets create DATABASE_URL --data-file=-
```

And in **steps 8, 11 and 12**, wherever you see `$PROJECT_ID:$REGION:food-db`, use
`$SQL_CONNECTION` instead. That single value is what goes in the
`GCP_CLOUDSQL_INSTANCE` variable.

---

## Step 4 — Create the four secrets

The deploy reads all four. **All four must exist**, including the Maps one — a missing
secret fails the deploy with `Secret not found`, which is a confusing error to debug
under time pressure.

A secret and its value are separate things in Secret Manager: `create` makes the
container, and each value is a numbered *version*. So `create` fails with
`already exists` the second time, and changing a value means **adding a version**, not
re-creating. The helper below does whichever is needed, so this step is safe to re-run
as many times as you like.

```bash
# Resolve the connection name rather than assuming the instance is called food-db.
export SQL_CONNECTION=$(gcloud sql instances describe ${SQL_INSTANCE:-food-db} \
  --format='value(connectionName)')
echo "SQL_CONNECTION = $SQL_CONNECTION"      # must not be empty

# Redis private IP — looked up, never typed by hand.
export REDIS_IP=$(gcloud redis instances describe food-cache --region=$REGION --format='value(host)')
echo "REDIS_IP = $REDIS_IP"                  # must not be empty

# Create the secret if it is new, add a version if it already exists.
set_secret() {
  local name="$1" value="$2"
  if gcloud secrets describe "$name" >/dev/null 2>&1; then
    printf '%s' "$value" | gcloud secrets versions add "$name" --data-file=- >/dev/null
    echo "UPDATED  $name"
  else
    printf '%s' "$value" | gcloud secrets create "$name" --data-file=- >/dev/null
    echo "CREATED  $name"
  fi
}

set_secret DATABASE_URL "postgresql://fooduser:${DB_PASSWORD}@/fooddelivery?host=/cloudsql/${SQL_CONNECTION}"
set_secret REDIS_URL    "redis://${REDIS_IP}:6379/0"
set_secret GOOGLE_MAPS_API_KEY "not-configured"

# Only if it does not exist yet — rotating this signs out every existing session.
gcloud secrets describe JWT_SECRET_KEY >/dev/null 2>&1 \
  || set_secret JWT_SECRET_KEY "$(openssl rand -hex 32)"
```

**Checkpoint:** all four listed, and the two connection strings read back correctly.

```bash
gcloud secrets list --format='value(name)'

# Prints your DB password to the terminal — use a window you can clear.
gcloud secrets versions access latest --secret=DATABASE_URL; echo
gcloud secrets versions access latest --secret=REDIS_URL; echo
```

`DATABASE_URL` must end in your real connection name and contain no line break.

> A running Cloud Run service does not pick up a new secret version on its own — the
> value is resolved when a revision starts. If you change a secret after deploying, you
> must redeploy. Before the first deploy, as now, there is nothing to redeploy.

---

## Step 5 — Let Cloud Run read the secrets

```bash
export RUNTIME_SA="$PROJECT_NUM-compute@developer.gserviceaccount.com"

for s in DATABASE_URL REDIS_URL JWT_SECRET_KEY GOOGLE_MAPS_API_KEY; do
  gcloud secrets add-iam-policy-binding $s \
    --member="serviceAccount:$RUNTIME_SA" \
    --role=roles/secretmanager.secretAccessor
done

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$RUNTIME_SA" --role=roles/cloudsql.client --condition=None
```

---

## Step 6 — Create the deploy service account

This is the identity GitHub Actions will borrow.

```bash
gcloud iam service-accounts create github-deployer \
  --display-name="GitHub Actions deployer"

export DEPLOYER="github-deployer@$PROJECT_ID.iam.gserviceaccount.com"

for role in roles/cloudbuild.builds.editor \
            roles/storage.admin \
            roles/artifactregistry.writer \
            roles/run.admin \
            roles/iam.serviceAccountUser \
            roles/serviceusage.serviceUsageConsumer; do
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$DEPLOYER" --role="$role" --condition=None
done
```

---

## Step 7 — Connect GitHub to GCP (Workload Identity)

This is what lets GitHub deploy without storing a password.

```bash
gcloud iam workload-identity-pools create github \
  --location=global --display-name="GitHub Actions"

gcloud iam workload-identity-pools providers create-oidc github-oidc \
  --location=global --workload-identity-pool=github \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository=='${GITHUB_REPO}'"

gcloud iam service-accounts add-iam-policy-binding "$DEPLOYER" \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/$PROJECT_NUM/locations/global/workloadIdentityPools/github/attribute.repository/$GITHUB_REPO"
```

The `--attribute-condition` restricts this to your repository only. Do not remove it.

---

## Step 8 — Print the values you will paste into GitHub

```bash
echo ""
echo "=========== SECRETS TAB (2) ==========="
echo "GCP_WIF_PROVIDER"
echo "  projects/$PROJECT_NUM/locations/global/workloadIdentityPools/github/providers/github-oidc"
echo "GCP_DEPLOY_SERVICE_ACCOUNT"
echo "  $DEPLOYER"
echo ""
echo "=========== VARIABLES TAB (3 now) ==========="
echo "GCP_PROJECT_ID"
echo "  $PROJECT_ID"
echo "GCP_CLOUDSQL_INSTANCE"
echo "  $(gcloud sql instances describe food-db --format='value(connectionName)')"
echo "GCP_VPC_CONNECTOR"
echo "  food-connector"
echo ""
```

**Keep this output on screen.** You need it for the next three steps.

---

## Step 9 — GitHub: delete the two wrong entries

Go to:
`https://github.com/pooja-66deg/food-delivery-system/settings/secrets/actions`

Under **Repository secrets**, delete both (trash icon):

- `PROJECT_ID`
- `REGION`

They are in the wrong place under the wrong names, so nothing reads them. You are
re-adding the project id as a *variable* in step 11.

---

## Step 10 — GitHub: add the 2 secrets

Same page, **Secrets** tab → **New repository secret**, twice:

| Name | Value |
|------|-------|
| `GCP_WIF_PROVIDER` | the `projects/...` line from step 8 |
| `GCP_DEPLOY_SERVICE_ACCOUNT` | the `github-deployer@...` line from step 8 |

Names must match exactly — they are case-sensitive.

---

## Step 11 — GitHub: add the 3 variables

Same page, click the **Variables** tab (next to Secrets) → **New repository variable**,
three times:

| Name | Value |
|------|-------|
| `GCP_PROJECT_ID` | your project id |
| `GCP_CLOUDSQL_INSTANCE` | the `PROJECT:REGION:food-db` line from step 8 |
| `GCP_VPC_CONNECTOR` | `food-connector` |

Add nothing else. Every other variable has a working default.

**Do not create a GitHub Environment.** The workflow makes `production` by itself. If
you create one and switch on "Required reviewers", every deploy will sit waiting for
approval instead of being automatic.

---

## Step 12 — The bootstrap deploy

This creates both Cloud Run services so they get URLs. **The app will not work yet —
that is expected and step 14 fixes it.**

Run from the repository root:

```bash
cd /Users/poojamishra/Desktop/66/food-delivery-system

gcloud builds submit --config infra/gcp/cloudbuild.yaml --substitutions=\
_REGION=$REGION,\
_AR_REPO=food-delivery,\
_CLOUDSQL_INSTANCE=$PROJECT_ID:$REGION:food-db,\
_VPC_CONNECTOR=food-connector,\
_TAG=bootstrap
```

Takes roughly 8–12 minutes. It runs the tests, builds both images, pushes them, and
deploys.

**Checkpoint:** the last lines say `Service [food-api] revision ... has been deployed`
and the same for `food-frontend`.

---

## Step 13 — Collect the two URLs

Cloud Run serves each service on **two** hostnames — the legacy
`SERVICE-HASH-REGIONCODE.a.run.app` and the newer
`SERVICE-PROJECTNUMBER.REGION.run.app`. `status.url` reports only one of them,
but a browser sends whichever one is in the address bar, and CORS matches the
`Origin` header by exact string. So `GCP_FE_URL` must list **both**, or the app
breaks on whichever hostname was left out.

```bash
export PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')

export API_URL=$(gcloud run services describe food-api      --region=$REGION --format='value(status.url)')
export FE_URL=$(gcloud run services describe food-frontend  --region=$REGION --format='value(status.url)')

# The other hostname for each service, derived rather than looked up.
export FE_URL_ALT="https://food-frontend-${PROJECT_NUMBER}.${REGION}.run.app"

echo ""
echo "GCP_API_URL  ->  $API_URL"
echo "GCP_FE_URL   ->  ${FE_URL},${FE_URL_ALT}"
echo ""
```

If `FE_URL` already came back in the `-${PROJECT_NUMBER}.${REGION}` form, then
`FE_URL_ALT` is the duplicate and the legacy one is what's missing — read it off
the service's page in the Cloud Run console. Listing a duplicate is harmless
(`cors_origin_list` de-duplicates), listing neither is what breaks.

Sanity-check the API is alive:

```bash
curl -s $API_URL/health
```

Expect `{"status":"healthy","environment":"production"}`.

---

## Step 14 — GitHub: add the last 2 variables

**Variables** tab → **New repository variable**, twice:

| Name | Value |
|------|-------|
| `GCP_API_URL` | the URL printed above |
| `GCP_FE_URL` | **both** frontend URLs printed above, comma-separated, no spaces |

Paste them exactly, including `https://` and **no trailing slash**.

`GCP_FE_URL` feeds two settings: the whole list becomes the `CORS_ORIGINS`
allowlist, while `FRONTEND_BASE_URL` (used to build emailed reset links) takes
only the first entry — so put the hostname you want in emails first.

You now have **2 secrets + 5 variables**. That is the complete set.

---

## Step 15 — Turn on automatic deploys

Your code is not committed yet. Push it as a branch and merge it — the merge is what
triggers the first real deploy.

```bash
git checkout -b feat/discovery-and-engagement
git add -A
git commit -m "feat: delivery zones, notification channels, discovery filters, reviews and favourites"
git push -u origin feat/discovery-and-engagement
```

Then on GitHub: open the pull request, wait for the checks to pass, and **Merge**.

Watch it run under the **Actions** tab. On a merge to `main` you get three jobs:
`backend`, `frontend`, then `deploy`.

**Checkpoint:** all three green. The `deploy` job's summary prints both live URLs.

---

## Step 16 — Verify the real thing

Open the `GCP_FE_URL` in a browser and walk the flow:

1. Register a **restaurant** account → **Manage** → create a restaurant → set it
   **Open** → add a category and a menu item.
2. Register a **customer** account → browse → **Add** to cart → **Cart** → add a
   delivery address in the same city → **Place order (COD)**.
3. As the restaurant, accept the order and advance it.

If step 2 fails with a network or CORS error, `GCP_FE_URL` is wrong or has a trailing
slash. Fix the variable and re-run the deploy from the Actions tab
(**Re-run all jobs**) — you do not need a new commit.

---

## From now on

Merge to `main` → deploys automatically. Nothing else to do.

**To roll back**, redeploy an earlier image (they are tagged with the commit sha):

```bash
gcloud run deploy food-api --region=$REGION \
  --image=$REGION-docker.pkg.dev/$PROJECT_ID/food-delivery/api:<older-sha>
```

---

## Two known limitations — worth knowing before a live demo

1. **Uploaded images do not survive a deploy.** Restaurant and menu images are written
   to the container's local disk, which Cloud Run discards on every new revision. For a
   demo: either upload images *after* your final deploy, or demo without them. (Tracked
   as §3.3 in [status-and-remaining-work.md](status-and-remaining-work.md).)
2. **Nothing runs the scheduled sweeps.** Orders a restaurant never accepts stay pending
   forever instead of auto-cancelling. It does not affect the happy path you will demo.

---

## If something breaks

| Symptom | Cause | Fix |
|---------|-------|-----|
| Deploy job fails instantly listing missing variables | A required variable is unset | Add it in the Variables tab; re-run the job |
| `Permission denied` / `unable to impersonate` | Step 6 or 7 incomplete | Re-run both steps, then re-run the job |
| `Secret not found` | A Secret Manager secret is missing | Re-run step 4 and confirm all four are listed |
| Frontend loads but every action errors | `GCP_FE_URL` wrong or has a trailing slash | Fix the variable, re-run the deploy |
| Frontend loads but calls go nowhere | `GCP_API_URL` wrong | Fix the variable, re-run the deploy |
| `Cloud SQL instance not found` | `GCP_CLOUDSQL_INSTANCE` is not `PROJECT:REGION:food-db` | Re-read it with the step 8 command |
| Deploy waits for approval | A GitHub Environment has Required reviewers on | Settings → Environments → production → turn it off |
