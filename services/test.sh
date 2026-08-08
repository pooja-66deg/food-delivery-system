#!/usr/bin/env bash
# Run each service's test suite.
#
#   ./services/test.sh            # every service
#   ./services/test.sh orders     # one of them
#
# One process per service, and that is not a style choice. Every service has a
# package literally named `app`, so a single pytest process would import one of
# them and then quietly serve that same module to every other service's tests.
# Separate processes are what keep the isolation the split is for — including in
# the test run.
set -uo pipefail

SERVICES="users restaurants orders payments delivery notifications admin"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

[ $# -gt 0 ] && SERVICES="$*"

failed=""
for svc in $SERVICES; do
  dir="$ROOT/services/$svc"
  if [ ! -d "$dir/tests" ]; then
    printf "%-16s no tests\n" "$svc"
    continue
  fi
  echo "== $svc"
  # PYTHONPATH: the service's own directory (for `app`) and the repo root
  # (for `shared`, which the image copies in alongside it).
  # `uv run` so this uses the project's virtualenv whether or not one is
  # activated — which it is not in CI.
  if PYTHONPATH="$dir:$ROOT" uv run --project "$ROOT" python -m pytest "$dir/tests" \
      -c "$ROOT/services/pytest.ini" -q --no-header 2>&1 | tail -6; then
    :
  else
    failed="$failed $svc"
  fi
done

echo
if [ -n "$failed" ]; then
  echo "FAILED:$failed"
  exit 1
fi
echo "all service suites passed"
