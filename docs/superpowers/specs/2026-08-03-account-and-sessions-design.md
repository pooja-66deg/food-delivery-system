# Design — Account management & session invalidation

Date: 2026-08-03
Branch: `feat/account-and-sessions`
Phase: D (see `2026-07-31-auth-forms-and-role-routing-design.md`)
Status: approved, implementing

## Problem

Five gaps, all in the users domain:

| Item | State before this branch |
| --- | --- |
| Address edit | `AddressPanel` adds and deletes only. `profile.py` has no `update_address`, and there is no `PATCH` route. |
| Email verification | Absent entirely — no column, no token flow, no UI. |
| Change password | An authenticated user cannot change their password; the only path is the signed-out reset. |
| Real reset email | `POST /auth/forgot-password` mints a token and returns it as `debug_token`. Nothing is ever sent. `EmailSender` also hardcodes the subject `"Order update"`. |
| Full logout invalidation | `get_current_user` never consults the JWT blocklist, so an access token stays valid for up to 30 minutes after logout. The frontend's `logout()` only clears `localStorage` and never calls `POST /auth/logout`, so the refresh token is never revoked at all. |

## Decisions

- **One branch for all five.** They share `schemas.py`, `router.py`, and the
  account UI; splitting would mean two rounds of conflicts in the same files.
- **Email verification is advisory.** Nothing is gated on it. Existing accounts
  land unverified, which is accurate and breaks nothing.
- **Reset mail uses the existing sender.** SendGrid when configured, log
  transport otherwise — the arrangement CLAUDE.md already documents. No new
  dependency, no SMTP service.
- **Revocation is two-layered:** a per-token jti blocklist for "log out of this
  device", and a per-user epoch for "log out of every device".

## Data model

One migration, `users` table only:

| Column | Type | Notes |
| --- | --- | --- |
| `is_email_verified` | `Boolean`, not null, `server_default false` | Advisory. |
| `session_generation` | `Integer`, not null, `server_default '0'` | Bumped to evict every session. Tokens carry it as a `gen` claim. |

A generation counter rather than a `sessions_valid_from` timestamp: JWT `iat`
has one-second granularity, so a timestamp epoch cannot distinguish the fresh
token issued *by* a password change from another device's token minted in the
same second — either the caller is signed out of their own tab or the other
device survives. An integer claim compared for equality has no such window. A
token with no `gen` claim reads as generation 0, so hand-built tokens and any
issued before this migration keep working until the first bump.

No new tables. Verification tokens live in Redis under
`email_verify:{token_hash}`, mirroring the existing `pwd_reset:{token_hash}`:
only the SHA-256 hash is stored, never the plaintext.

New settings: `frontend_base_url: str = "http://localhost:5173"` and
`email_verification_ttl_seconds: int = 86400`, beside the existing
`password_reset_ttl_seconds`. All three are listed in `.env.example`.

## Backend

### `src/modules/users/tokens.py` (new)

`issue_single_use(redis, prefix, user_id, ttl) -> str` and
`consume_single_use(redis, prefix, token) -> int`. Hash-store-consume is
currently inline in `service.py`; verification needs the same mechanics, so it
is extracted rather than duplicated. Pure Redis + hashing, no ORM — trivially
testable.

### Endpoints

| Route | Behaviour |
| --- | --- |
| `PATCH /users/me/addresses/{id}` | `AddressUpdate`, every field optional. Reuses `_owned_address` for the not-yours 404 and `_clear_default` when `is_default` flips true. Returns `AddressResponse`. |
| `POST /users/me/change-password` | Verifies `current_password` (401 if wrong), rehashes, bumps `session_generation`. Returns a **fresh `TokenResponse`** carrying the new generation, so the calling tab survives the eviction it triggered. Rate-limited. |
| `POST /auth/verify-email/request` | Authenticated, rate-limited. Dispatches `EMAIL` with `{frontend_base_url}/verify-email?token=…`. `debug_token` in non-production only. 202. |
| `POST /auth/verify-email/confirm` | Public, `{token}` → sets `is_email_verified`, 204. Public because the link is opened from a mail client that may not be signed in. Already-verified is idempotent, not an error. |
| `POST /auth/logout` | Keeps its `refresh_token` body; additionally blocklists the bearer access token's jti when the header is present. 204 regardless, as today. |
| `POST /auth/forgot-password` | Now dispatches the reset mail. Response body unchanged. |
| `POST /auth/reset-password` | Also bumps `session_generation` — a reset must evict whoever locked the user out. |

### `get_current_user`

Two added checks, both raising the existing `UnauthorizedException`:

1. The access token's jti is not blocklisted (one Redis `GET`; the dependency
   gains `redis=Depends(get_redis)`, already overridden globally in
   `tests/conftest.py`).
2. `payload.gen == user.session_generation` (absent `gen` reads as 0). Free —
   the user row is already loaded. `refresh_tokens` enforces the same check, so
   an evicted refresh token cannot mint a live pair.

### Senders

`dispatch(channel, to, message, subject=...)` and
`EmailSender.send(..., subject=...)`, defaulting to today's `"Order update"` so
no existing caller changes. Without this a password-reset mail arrives titled
"Order update".

## Frontend

`AccountPage.tsx` (263 lines) splits into `frontend/src/pages/account/`:

```
account/
  AccountPage.tsx        role gating + layout only
  ProfilePanel.tsx       extracted unchanged
  AddressPanel.tsx       extracted; gains edit
  AddressForm.tsx        one form, add-or-edit mode
  SecurityPanel.tsx      change password (PasswordField ×3)
  VerificationNotice.tsx verified chip / resend button
```

Plus `pages/VerifyEmailPage.tsx` (public, reads `?token=`) and a public
`/verify-email` route in `App.tsx`.

`AuthContext.logout` becomes async: it calls `POST /auth/logout` with the stored
refresh token, then clears storage — and clears storage even if the call fails,
so a network error can never strand a user signed in. A new `replaceTokens`
stores the pair returned by change-password.

`api/auth.ts` gains `updateAddress`, `changePassword`, `requestVerification`,
`confirmVerification`, `logout`, and `is_email_verified` on `User`.

## Test plan

Written test-first per the repository TDD convention.

| Test | Asserts |
| --- | --- |
| `tests/modules/users/test_tokens.py` | Issue then consume returns the user id; a second consume fails; an unknown token fails |
| `tests/modules/users/test_change_password.py` | Wrong current password 401s; success returns a usable new pair; the old access token is dead afterwards; the old refresh token is dead afterwards |
| `tests/modules/users/test_email_verification.py` | `me` starts `is_email_verified: false`; request → confirm flips it; a reused token 401s; an unknown token 401s; confirming twice is idempotent |
| `tests/modules/users/test_address_update.py` | Partial update changes only the named fields; promoting one address to default demotes the other; another user's address 404s |
| `tests/modules/users/test_auth_hardening.py` (extend) | The access token is rejected immediately after logout; logout without a bearer still revokes the refresh token |
| `tests/modules/users/test_password_reset.py` (extend) | Forgot-password dispatches an `EMAIL` containing the reset link; an unknown address sends nothing; a reset evicts existing sessions |
| `tests/modules/users/test_dependencies.py` (extend) | `get_current_user` rejects a revoked token and a stale generation (signature gains `redis`) |
| `frontend/tests/pages/account/SecurityPanel.test.tsx` | Mismatched confirmation blocks submit; success shows confirmation and stores the new tokens |
| `frontend/tests/pages/account/AddressPanel.test.tsx` | Edit prefills the form and `PATCH`es; cancel restores the list |
| `frontend/tests/pages/account/VerificationNotice.test.tsx` | Unverified shows resend; verified shows the chip and no button |
| `frontend/tests/auth/AuthContext.test.tsx` | `logout` calls the endpoint and clears storage; storage is cleared even when the call rejects; no call when there is no refresh token |

`frontend/tests/pages/AccountPage.test.tsx` moves to
`frontend/tests/pages/account/` alongside the split it covers, and gains a case
asserting the password panel is offered to every role.

## Verification

```bash
pytest                         # backend, must stay green
flake8 src                     # must stay clean
cd frontend && npm test        # vitest
cd frontend && npm run build   # tsc + vite
alembic upgrade head           # migration applies
```

## Out of scope

- A server-side session table and per-device revocation UI.
- Gating any action on `is_email_verified`.
- Password strength rules beyond the existing 8-character minimum.
- Email *change* (only verification of the address on file).
