set -euo pipefail
SERVICES="users restaurants orders payments delivery notifications admin"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PGHOST_="${SERVICE_DB_HOST:-localhost}"
PGUSER_="${SERVICE_DB_USER:-fooduser}"
PGPASS_="${SERVICE_DB_PASSWORD:-foodpass}"

port_for() {
  case "$1" in
    orders) echo 5433 ;;
    payments) echo 5434 ;;
    users) echo 5435 ;;
    restaurants) echo 5436 ;;
    delivery) echo 5437 ;;
    notifications) echo 5438 ;;
    admin) echo 5439 ;;
    # Every name in SERVICES needs an entry here, or `all` dies partway through
    # having already migrated the services before it.
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
  if [ -n "${DATABASE_URL:-}" ]; then
    echo "refusing: DATABASE_URL is set and 'all' would send every service to it." >&2
    exit 2
  fi
  for svc in $SERVICES; do run_one "$svc" "$@"; done
else
  run_one "$TARGET" "$@"
fi
