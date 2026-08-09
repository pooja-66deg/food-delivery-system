#!/usr/bin/env bash
# One-command dev launcher for the Food Delivery Platform.
#
# Usage:
#   ./run.sh                Start the whole stack in Docker (recommended)
#   ./run.sh --seed         ...and create the dev accounts once it is up
#   ./run.sh --frontend     Backend in Docker, frontend on the host for hot reload
#   ./run.sh --logs         Follow the logs of the running stack
#   ./run.sh --down         Stop everything (volumes, and your data, survive)
#   ./run.sh --reset        Stop and DELETE every volume — all local data is lost
#
# ---------------------------------------------------------------------------
# This used to run `uvicorn src.main:app` — one process serving every domain,
# because the platform was a modular monolith. It is seven services now, `src/`
# no longer exists, and there is no single process to start: a service needs its
# own database, the gateway needs the services, and the frontend needs the
# gateway. Docker Compose is what expresses that, so this script drives it
# rather than trying to reproduce it.
#
# The one thing still worth running on the host is the frontend, because Vite's
# hot reload is the difference between a one-second and a one-minute edit loop.
# That is what --frontend is for; it points the dev server at the gateway in
# Docker.
# ---------------------------------------------------------------------------
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

COMPOSE="docker compose -f infra/compose/docker-compose.yml"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
GATEWAY_URL="${GATEWAY_URL:-http://localhost:8080}"

MODE="stack"
SEED=0
while [ $# -gt 0 ]; do
  case "$1" in
    --seed)     SEED=1 ;;
    --frontend) MODE="frontend" ;;
    --logs)     MODE="logs" ;;
    --down)     MODE="down" ;;
    --reset)    MODE="reset" ;;
    -h|--help)  awk 'NR==1{next} /^#/{sub(/^# ?/,"");print;next}{exit}' "$0"; exit 0 ;;
    *) echo "unknown option: $1 (try --help)"; exit 1 ;;
  esac
  shift
done

if ! docker info >/dev/null 2>&1; then
  echo "Docker is not running. Start Docker Desktop and try again." >&2
  exit 1
fi

case "$MODE" in
  logs)
    exec $COMPOSE logs -f
    ;;

  down)
    echo "[infra] stopping (volumes kept — your data survives)..."
    exec $COMPOSE down
    ;;

  reset)
    # -v is the destructive one, so it is its own flag and says so. Wiping the
    # users database is how every account, address and favourite disappears
    # while the other services keep rows pointing at ids that no longer exist.
    echo "This deletes every local database volume: all accounts, restaurants,"
    echo "orders and menus are lost. The stack comes back empty."
    printf "Type 'reset' to confirm: "
    read -r reply
    [ "$reply" = "reset" ] || { echo "Cancelled."; exit 1; }
    $COMPOSE down -v
    echo "Gone. Bring it back with: ./run.sh --seed"
    exit 0
    ;;

  frontend)
    echo "[frontend] http://localhost:$FRONTEND_PORT  ->  API at $GATEWAY_URL"
    echo "[frontend] the backend must already be up: ./run.sh"
    [ -d "$ROOT/frontend/node_modules" ] || ( cd frontend && npm install )
    cd frontend
    exec npm run dev -- --port "$FRONTEND_PORT"
    ;;
esac

# ---------- the whole stack ----------
echo "[infra] building and starting the stack (first run pulls images — give it a few minutes)..."
$COMPOSE up -d --build || { echo "[infra] compose failed." >&2; exit 1; }

# Readiness, not a fixed sleep: image build time varies enormously between a
# cold and a warm cache, and a sleep is either wrong or wasteful.
echo -n "[infra] waiting for the gateway"
for _ in $(seq 1 60); do
  if curl -sS -o /dev/null --max-time 2 "$GATEWAY_URL/health" 2>/dev/null; then
    echo " — up."
    break
  fi
  echo -n "."
  sleep 2
done

if [ "$SEED" = "1" ]; then
  echo
  ./infra/compose/seed-dev.sh "$GATEWAY_URL"
fi

cat <<EOF

  Frontend        http://localhost:$FRONTEND_PORT
  API gateway     $GATEWAY_URL

  Logs            ./run.sh --logs
  Stop            ./run.sh --down
  Dev accounts    ./infra/compose/seed-dev.sh

EOF
