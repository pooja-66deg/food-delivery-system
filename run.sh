#!/usr/bin/env bash
# One-command dev launcher for the Food Delivery Platform.
#
# Runs the backend API (all domains - it is a modular monolith, so one process
# = all services) and the customer frontend together, with prefixed logs and a
# clean shutdown of both on Ctrl+C.
#
# Usage:
#   ./run.sh              Start backend + frontend
#   ./run.sh --infra      Also start Postgres/Redis/Kafka via docker compose
#   ./run.sh --install    Install backend + frontend dependencies, then run
#   ./run.sh --backend    Run only the backend
#   ./run.sh --frontend   Run only the frontend
#   ./run.sh --no-reload  Disable backend auto-reload
#
# The backend needs PostgreSQL and Redis reachable. Start them yourself, or pass
# --infra to bring them up with Docker. Connection settings default to the
# values in infra/compose/docker-compose.yml and can be overridden via environment variables.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# ---------- parse flags ----------
INFRA=0; INSTALL=0; ONLY=""; RELOAD="--reload"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
while [ $# -gt 0 ]; do
  case "$1" in
    --infra)         INFRA=1 ;;
    --install)       INSTALL=1 ;;
    --backend)       ONLY="backend" ;;
    --frontend)      ONLY="frontend" ;;
    --no-reload)     RELOAD="" ;;
    --backend-port)  BACKEND_PORT="$2"; shift ;;
    --frontend-port) FRONTEND_PORT="$2"; shift ;;
    -h|--help)       awk 'NR==1{next} /^#/{sub(/^# ?/,"");print;next}{exit}' "$0"; exit 0 ;;
    *) echo "unknown option: $1 (try --help)"; exit 1 ;;
  esac
  shift
done

# ---------- pick interpreters ----------
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) IS_WIN=1; PYTHON="$ROOT/.venv/Scripts/python.exe" ;;
  *)                    IS_WIN=0; PYTHON="$ROOT/.venv/bin/python" ;;
esac
[ -x "$PYTHON" ] || PYTHON="python"   # fall back to system python

# ---------- backend env defaults (mirror infra/compose/docker-compose.yml) ----------
export DATABASE_URL="${DATABASE_URL:-postgresql://fooduser:foodpass@localhost:5432/fooddelivery}"
export REDIS_URL="${REDIS_URL:-redis://localhost:6379/0}"
export KAFKA_BROKERS="${KAFKA_BROKERS:-localhost:9092}"
export JWT_SECRET_KEY="${JWT_SECRET_KEY:-dev-secret-change-me}"
export ENVIRONMENT="${ENVIRONMENT:-development}"
export PYTHONUNBUFFERED=1 FORCE_COLOR=1

# ---------- optional: install deps ----------
if [ "$INSTALL" = "1" ]; then
  echo "[backend]  installing Python dependencies..."
  if command -v uv >/dev/null 2>&1; then
    uv sync --extra dev --no-install-project
  else
    echo "[backend]  uv not found - install it from https://docs.astral.sh/uv/ ."
    echo "[backend]  falling back to pip (resolves fresh, ignores uv.lock)."
    "$PYTHON" -m pip install -e ".[dev]"
  fi
  echo "[frontend] installing npm dependencies..."
  ( cd frontend && npm install )
fi

# ---------- optional: infra via docker ----------
if [ "$INFRA" = "1" ]; then
  if docker info >/dev/null 2>&1; then
    echo "[infra] bringing up Postgres/Redis/Kafka via docker compose..."
    docker compose -f infra/compose/docker-compose.yml up -d postgres redis kafka || echo "[infra] docker compose failed; continuing."
  else
    echo "[infra] Docker not available - start Postgres/Redis yourself."
  fi
fi

# ---------- warnings ----------
if [ "$ONLY" != "frontend" ] && [ ! -e "$ROOT/.venv" ]; then
  echo "[backend]  no .venv found - using system Python. If imports fail: ./run.sh --install"
fi
if [ "$ONLY" != "backend" ] && [ ! -d "$ROOT/frontend/node_modules" ]; then
  echo "[frontend] frontend/node_modules missing. Run: ./run.sh --install"
fi

# ---------- shutdown ----------
PIDS=()
PORTS=()

# Windows: kill whatever is LISTENING on a port (and its tree). More reliable
# than tree-walking, because npm detaches node across the cmd/job boundary.
kill_port_win() {
  local port="$1" wp
  for wp in $(netstat -ano 2>/dev/null | grep -i listening | grep -E "[:.]$port[[:space:]]" | awk '{print $NF}' | sort -u); do
    [ -n "$wp" ] && MSYS_NO_PATHCONV=1 taskkill /F /T /PID "$wp" >/dev/null 2>&1 || true
  done
}

cleanup() {
  trap - INT TERM EXIT
  echo
  echo "[infra] stopping..."
  if [ "$IS_WIN" = "1" ]; then
    for port in "${PORTS[@]:-}"; do [ -n "$port" ] && kill_port_win "$port"; done
    for pid in "${PIDS[@]:-}"; do [ -n "$pid" ] && kill "$pid" 2>/dev/null || true; done
  else
    kill 0 2>/dev/null || true
  fi
}
trap cleanup INT TERM EXIT

# ---------- launch (each in its own subshell so we can kill its tree) ----------
if [ "$ONLY" != "frontend" ]; then
  echo "[backend]  http://localhost:$BACKEND_PORT"
  ( "$PYTHON" -m uvicorn src.main:app --host 0.0.0.0 --port "$BACKEND_PORT" $RELOAD 2>&1 \
      | sed 's/^/[backend] /' ) &
  PIDS+=($!); PORTS+=("$BACKEND_PORT")
fi

if [ "$ONLY" != "backend" ]; then
  echo "[frontend] http://localhost:$FRONTEND_PORT"
  ( cd frontend && npm run dev -- --port "$FRONTEND_PORT" 2>&1 \
      | sed 's/^/[frontend] /' ) &
  PIDS+=($!); PORTS+=("$FRONTEND_PORT")
fi

echo "[infra] press Ctrl+C to stop everything."
wait
