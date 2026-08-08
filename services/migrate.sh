#!/usr/bin/env bash
# Run a service's migrations against its own database.
#
#   ./services/migrate.sh users upgrade head
#   ./services/migrate.sh all upgrade head
#
# Each service reads DATABASE_URL from the environment. Passing "all" is a
# convenience for local setup only — in production every service migrates itself
# as part of its own deploy, which is the point of separate chains. A single
# command that migrates everything is a single command that can break
# everything.
set -euo pipefail

SERVICES="users restaurants orders payments delivery notifications"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Host/port of the Postgres holding the per-service databases. Overridable so
# the same script works against compose (one container per service), a single
# local Postgres with six databases, or Cloud SQL.
PGHOST_="${SERVICE_DB_HOST:-localhost}"
PGUSER_="${SERVICE_DB_USER:-fooduser}"
PGPASS_="${SERVICE_DB_PASSWORD:-foodpass}"

# Compose maps each service's Postgres to its own host port.
port_for() {
  case "$1" in
    orders) echo 5433 ;;
    payments) echo 5434 ;;
    users) echo 5435 ;;
    restaurants) echo 5436 ;;
    delivery) echo 5437 ;;
    notifications) echo 5438 ;;
    *) echo "unknown service: $1" >&2; exit 2 ;;
  esac
}

usage() {
  echo "usage: $0 <service|all> <alembic args...>" >&2
  echo "  services: $SERVICES" >&2
  exit 2
}

[ $# -ge 2 ] || usage
TARGET="$1"; shift

run_one() {
  local svc="$1"; shift
  local url="${DATABASE_URL:-postgresql://${PGUSER_}:${PGPASS_}@${PGHOST_}:$(port_for "$svc")/${svc}_db}"
  echo "== $svc: alembic $* =="
  ( cd "$ROOT/services/$svc" && DATABASE_URL="$url" uv run --project "$ROOT" alembic "$@" )
}

if [ "$TARGET" = "all" ]; then
  # DATABASE_URL would point every service at one database, which is the exact
  # mistake this layout exists to prevent.
  if [ -n "${DATABASE_URL:-}" ]; then
    echo "refusing: DATABASE_URL is set and 'all' would send every service to it." >&2
    exit 2
  fi
  for svc in $SERVICES; do run_one "$svc" "$@"; done
else
  run_one "$TARGET" "$@"
fi
