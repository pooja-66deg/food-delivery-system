#!/usr/bin/env bash
# Create the per-service database secrets, and let Cloud Run read every secret
# the platform mounts — not just the database ones.
#
# That distinction is the whole reason the second loop exists. This script used
# to grant secretAccessor only inside the per-service DATABASE_URL loop, so the
# ten shared secrets (Stripe, SendGrid, Twilio, Maps, JWT, Redis) never got a
# binding from anything in the repository. Adding a secret to cloudbuild.yaml's
# --set-secrets therefore deployed cleanly and failed at *revision* time with
# "Permission denied on secret ... for Revision service account", which reads
# like a Cloud Run problem rather than a missing line here.
#
#   ./infra/gcp/create-secrets.sh PROJECT_ID [REGION]
#
# A script rather than a snippet in the README, because the README's version was
# a `for` loop and a loop pasted into a terminal line by line silently runs with
# an empty loop variable — which creates a secret literally named
# `_DATABASE_URL` and looks like it worked.
#
# The password is read from the existing DATABASE_URL secret rather than asked
# for: Cloud SQL passwords cannot be retrieved, and that secret is where this
# one already is. Pass DB_PASSWORD in the environment to override.
#
# Safe to re-run: an existing secret is left alone rather than replaced, so this
# never quietly rotates a credential something is using.
set -euo pipefail

PROJECT_ID="${1:?usage: $0 PROJECT_ID [REGION]}"
REGION="${2:-us-central1}"
INSTANCE="${CLOUDSQL_INSTANCE_NAME:-food-db}"
DB_USER="${DB_USER:-fooduser}"

SERVICES="users restaurants orders payments delivery notifications admin"

# Every non-database secret named in cloudbuild.yaml's --set-secrets. Keep this
# list in step with that file: a name here that the pipeline does not mount is
# harmless, a name the pipeline mounts that is missing here is a deploy that
# fails at revision time.
#
#   grep -o '[A-Z_]*=[A-Z_]*:latest' infra/gcp/cloudbuild.yaml \
#     | sed 's/.*=//;s/:latest//' | sort -u
#
# These are not created here — their values come from Stripe, SendGrid, Twilio
# and the Cloud Console, so there is nothing to generate. This script only
# grants access to the ones that exist.
SHARED_SECRETS="JWT_SECRET_KEY REDIS_URL GOOGLE_MAPS_API_KEY
                STRIPE_SECRET_KEY STRIPE_WEBHOOK_SECRET
                SENDGRID_API_KEY SENDGRID_FROM_EMAIL
                TWILIO_ACCOUNT_SID TWILIO_AUTH_TOKEN TWILIO_PHONE_NUMBER
                ADMIN_GATE_PASSWORD BOOTSTRAP_SECRET"

# The two secrets above that this platform owns outright. Unlike a Stripe key
# there is no external account to copy a value from — any sufficiently random
# string will do — so leaving them for a human to invent means a weak one chosen
# under deploy pressure, or a deploy blocked on nobody knowing what to put.
#
# Generated only when absent, like everything else here, so re-running never
# rotates a secret something is already using.
GENERATED_SECRETS="ADMIN_GATE_PASSWORD BOOTSTRAP_SECRET"

# --- the password ----------------------------------------------------------
if [ -z "${DB_PASSWORD:-}" ]; then
  echo "Reading the password out of the existing DATABASE_URL secret..."
  existing=$(gcloud secrets versions access latest --secret=DATABASE_URL \
    --project="$PROJECT_ID" 2>/dev/null || true)
  DB_PASSWORD=$(printf '%s' "$existing" | sed -E 's|^postgresql://[^:]+:([^@]+)@.*|\1|')
  if [ -z "$DB_PASSWORD" ] || [ "$DB_PASSWORD" = "$existing" ]; then
    echo "Could not read it. Set one explicitly and re-run:" >&2
    echo "  DB_PASSWORD='...' $0 $PROJECT_ID $REGION" >&2
    echo "Or reset it — safe now that the monolith is gone:" >&2
    echo "  gcloud sql users set-password $DB_USER --instance=$INSTANCE --password='...'" >&2
    exit 1
  fi
  echo "  found (${#DB_PASSWORD} characters)"
fi

PROJECT_NUM=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
RUNTIME_SA="$PROJECT_NUM-compute@developer.gserviceaccount.com"
echo "Cloud Run runs as: $RUNTIME_SA"
echo

for svc in $SERVICES; do
  upper=$(printf '%s' "$svc" | tr '[:lower:]' '[:upper:]')
  name="${upper}_DATABASE_URL"

  if gcloud secrets describe "$name" --project="$PROJECT_ID" >/dev/null 2>&1; then
    echo "  $name — already exists, leaving it"
  else
    # The Cloud SQL unix socket, not a host:port. Each service's engine adds
    # +asyncpg itself; alembic strips it back off for its sync driver.
    printf 'postgresql://%s:%s@/%s_db?host=/cloudsql/%s:%s:%s' \
      "$DB_USER" "$DB_PASSWORD" "$svc" "$PROJECT_ID" "$REGION" "$INSTANCE" \
      | gcloud secrets create "$name" --data-file=- --project="$PROJECT_ID" >/dev/null
    echo "  $name — created"
  fi

  gcloud secrets add-iam-policy-binding "$name" \
    --member="serviceAccount:$RUNTIME_SA" \
    --role=roles/secretmanager.secretAccessor \
    --project="$PROJECT_ID" --quiet >/dev/null
done


# --- the ones we can generate ----------------------------------------------
# Created before the binding loop below, so a fresh project gets a value and an
# IAM binding in a single run rather than being told to come back.
echo
for name in $GENERATED_SECRETS; do
  if gcloud secrets describe "$name" --project="$PROJECT_ID" >/dev/null 2>&1; then
    echo "  $name — already exists, leaving it"
  else
    # openssl rather than $RANDOM: the latter is 15 bits of a seeded PRNG, which
    # is a guessable password however long the string built from it looks.
    openssl rand -base64 36 | tr -d '\n=+/' \
      | gcloud secrets create "$name" --data-file=- --project="$PROJECT_ID" >/dev/null
    echo "  $name — created (random)"
  fi
done

echo
echo "The admin console gate password is now in Secret Manager. Read it with:"
echo "  gcloud secrets versions access latest --secret=ADMIN_GATE_PASSWORD --project=$PROJECT_ID"
echo "Share it with whoever operates the console — it is never sent to the browser."

# --- the shared secrets ----------------------------------------------------
# Only the binding, never the value. A missing one is reported rather than
# created: an empty STRIPE_SECRET_KEY would deploy happily and fail at the first
# charge, which is far worse than a deploy that refuses to start.
echo
missing=""
for name in $SHARED_SECRETS; do
  if gcloud secrets describe "$name" --project="$PROJECT_ID" >/dev/null 2>&1; then
    gcloud secrets add-iam-policy-binding "$name" \
      --member="serviceAccount:$RUNTIME_SA" \
      --role=roles/secretmanager.secretAccessor \
      --project="$PROJECT_ID" --quiet >/dev/null
    echo "  $name — access granted"
  else
    missing="$missing $name"
    echo "  $name — MISSING"
  fi
done

if [ -n "$missing" ]; then
  echo
  echo "These secrets do not exist yet. Every service that mounts one will fail" >&2
  echo "to start, with 'Permission denied on secret' — the same message you get" >&2
  echo "for a missing binding. Create each, then re-run this script:" >&2
  for name in $missing; do
    echo "  printf '%s' 'VALUE' | gcloud secrets create $name --data-file=- --project=$PROJECT_ID" >&2
  done
fi

echo
echo "--- database secrets now ---"
gcloud secrets list --project="$PROJECT_ID" --format='value(name)' | grep DATABASE_URL | sed 's/^/  /'
echo
echo "Expect seven <SERVICE>_DATABASE_URL names plus the old DATABASE_URL."
echo "A secret named just _DATABASE_URL means a loop ran with an empty variable —"
echo "delete it: gcloud secrets delete _DATABASE_URL --project=$PROJECT_ID"
