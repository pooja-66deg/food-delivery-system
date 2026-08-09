#!/usr/bin/env bash
# Recreate a usable set of local dev accounts.
#
#   ./infra/compose/seed-dev.sh [GATEWAY_URL]
#
# The compose stack's databases are volumes, not fixtures — nothing recreates an
# account after the users database is emptied, and the other services keep going
# because they never held a foreign key to it. The result is a stack that looks
# healthy while every login fails: restaurants still lists venues owned by an
# ``owner_id`` that resolves to nobody.
#
# This registers one account per role through the public API, so the accounts are
# built the same way a real signup builds them — password hashing, phone
# normalisation, the user-events the other services consume. Seeding the table
# directly would skip all three and leave the read-models empty.
#
# Re-runnable: an account that already exists is reported and reused, never
# replaced, so this never rotates the password of an account you are signed in
# as.
#
# ``admin`` is not offered by public registration (see SelfServiceRole), so that
# one row is promoted with SQL after the fact — the one thing here that has to
# reach past the API.
set -uo pipefail

GATEWAY="${1:-http://localhost:8080}"
PASSWORD="${SEED_PASSWORD:-devpassword1}"
USERS_DB_CONTAINER="${USERS_DB_CONTAINER:-fooddelivery_postgres_users}"
DB_USER="${DB_USER:-fooduser}"

command -v jq >/dev/null 2>&1 || { echo "jq is required: brew install jq" >&2; exit 1; }

# --- helpers ---------------------------------------------------------------

api() {  # api METHOD PATH [JSON_BODY] [BEARER]
  local method="$1" path="$2" body="${3:-}" token="${4:-}"
  local args=(-sS -X "$method" "$GATEWAY$path" -H 'Content-Type: application/json'
              -w '\n%{http_code}')
  [ -n "$body" ]  && args+=(-d "$body")
  [ -n "$token" ] && args+=(-H "Authorization: Bearer $token")
  curl "${args[@]}"
}

# Splits api()'s trailing status line off the body. Two globals rather than a
# subshell so the caller keeps both without re-running the request.
call() {
  local out; out="$(api "$@")"
  STATUS="${out##*$'\n'}"
  BODY="${out%$'\n'*}"
}

register() {  # register ROLE EMAIL PHONE FIRST LAST -> echoes the user id
  local role="$1" email="$2" phone="$3" first="$4" last="$5"
  call POST /api/auth/register "$(jq -nc \
    --arg e "$email" --arg p "$phone" --arg f "$first" \
    --arg l "$last" --arg pw "$PASSWORD" --arg r "$role" \
    '{email:$e, phone:$p, first_name:$f, last_name:$l, password:$pw, role:$r}')"

  case "$STATUS" in
    201) echo "  $role  $email  created" >&2; jq -r '.id' <<<"$BODY" ;;
    409) echo "  $role  $email  already exists, reusing" >&2; login_id "$email" ;;
    *)   echo "  $role  $email  FAILED ($STATUS): $BODY" >&2; echo "" ;;
  esac
}

token_for() {  # token_for EMAIL -> echoes an access token
  call POST /api/auth/login "$(jq -nc --arg e "$1" --arg p "$PASSWORD" \
    '{email:$e, password:$p}')"
  [ "$STATUS" = "200" ] || { echo "" ; return; }
  jq -r '.access_token' <<<"$BODY"
}

login_id() {  # login_id EMAIL -> echoes the user id of an existing account
  local t; t="$(token_for "$1")"
  [ -n "$t" ] || { echo ""; return; }
  call GET /api/users/me "" "$t"
  jq -r '.id' <<<"$BODY"
}

# --- is anything listening? ------------------------------------------------

if ! curl -sS -o /dev/null --max-time 5 "$GATEWAY/api/restaurants" 2>/dev/null; then
  echo "No gateway at $GATEWAY." >&2
  echo "Start the stack first:" >&2
  echo "  docker compose -f infra/compose/docker-compose.yml up -d" >&2
  exit 1
fi

echo "Seeding via $GATEWAY (password: $PASSWORD)"
echo

OWNER_ID="$(register restaurant owner@example.com    '+919876500001' Olivia Owner)"
CUSTOMER_ID="$(register customer  customer@example.com '+919876500002' Chris  Customer)"
DRIVER_ID="$(register driver     driver@example.com   '+919876500003' Dana   Driver)"
ADMIN_ID="$(register customer    admin@example.com    '+919876500004' Avery  Admin)"

# --- promote the admin -----------------------------------------------------
# Registered as a customer above because SelfServiceRole refuses "admin", then
# promoted here. The role lives in the JWT, so this only takes effect on the
# next login — an admin who was already signed in keeps a customer token until
# it expires.
if [ -n "$ADMIN_ID" ]; then
  docker exec "$USERS_DB_CONTAINER" psql -U "$DB_USER" -d users_db -q \
    -c "UPDATE users SET role='admin' WHERE email='admin@example.com'" >/dev/null 2>&1 \
    && echo "  admin  admin@example.com  promoted to role=admin" \
    || echo "  admin  admin@example.com  COULD NOT PROMOTE (is $USERS_DB_CONTAINER running?)" >&2
fi

# --- adopt orphaned restaurants -------------------------------------------
# Restaurants outlive the users database, so rows can be left pointing at an
# owner_id that no longer resolves. Handing them to the seeded owner is what
# makes their existing menus reachable again — otherwise the data is present,
# listed to customers, and editable by nobody.
echo
if [ -n "$OWNER_ID" ]; then
  ORPHANS=$(docker exec fooddelivery_postgres_restaurants psql -U "$DB_USER" \
    -d restaurants_db -tAc "SELECT count(*) FROM restaurants WHERE owner_id <> $OWNER_ID" 2>/dev/null || echo "?")
  if [ "$ORPHANS" != "?" ] && [ "${ORPHANS:-0}" -gt 0 ]; then
    docker exec fooddelivery_postgres_restaurants psql -U "$DB_USER" -d restaurants_db -q \
      -c "UPDATE restaurants SET owner_id = $OWNER_ID WHERE owner_id <> $OWNER_ID" >/dev/null
    echo "  adopted $ORPHANS restaurant(s) -> owner_id=$OWNER_ID"
  else
    echo "  no orphaned restaurants to adopt"
  fi
fi

echo
echo "--- sign in with ---"
printf '  %-28s %s\n' "owner@example.com"    "$PASSWORD  (restaurant)"
printf '  %-28s %s\n' "customer@example.com" "$PASSWORD  (customer)"
printf '  %-28s %s\n' "driver@example.com"   "$PASSWORD  (driver)"
printf '  %-28s %s\n' "admin@example.com"    "$PASSWORD  (admin)"
echo
echo "Sign out and back in if the browser still holds a token from before —"
echo "it names a user id that no longer exists, and every call will 401."
