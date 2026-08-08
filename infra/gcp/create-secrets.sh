#!/usr/bin/env bash
# Create the per-service database secrets, and let Cloud Run read them.
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

echo
echo "--- database secrets now ---"
gcloud secrets list --project="$PROJECT_ID" --format='value(name)' | grep DATABASE_URL | sed 's/^/  /'
echo
echo "Expect seven <SERVICE>_DATABASE_URL names plus the old DATABASE_URL."
echo "A secret named just _DATABASE_URL means a loop ran with an empty variable —"
echo "delete it: gcloud secrets delete _DATABASE_URL --project=$PROJECT_ID"
