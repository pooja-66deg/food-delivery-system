# Email verification on registration — design

**Date:** 2026-08-05
**Status:** approved, ready for implementation planning

## Problem

Registering an account does not prompt the user to verify their email address.
The verification machinery is already built and working, but nothing triggers it
and nothing surfaces it, so `users.is_email_verified` stays `false` forever for
every real account.

## What already exists

Verification is roughly 80% implemented. None of this needs to be built:

| Piece | Location |
|---|---|
| `users.is_email_verified` column | `src/modules/users/models.py:28` |
| `POST /auth/verify-email/request` | `src/modules/users/router.py:125` |
| `POST /auth/verify-email/confirm` | `src/modules/users/router.py:148` |
| Single-use hashed Redis token, 24h TTL | `src/modules/users/tokens.py` |
| `service.request_email_verification` / `verify_email` | `src/modules/users/service.py:77,84` |
| Frontend `/verify-email` route | `frontend/src/App.tsx:32` |
| `VerifyEmailPage` (works signed out) | `frontend/src/pages/VerifyEmailPage.tsx` |
| Account-page resend card | `frontend/src/pages/account/VerificationNotice.tsx` |
| API client methods | `frontend/src/api/auth.ts:97,103` |

## The four gaps

1. **Registration never triggers it.** `register` rate-limits, creates the user,
   returns. No token, no mail.
2. **The prompt is buried.** `VerificationNotice` renders only on the Account
   page (`AccountPage.tsx:41`). A new user must go hunting for it.
3. **Nothing is gated on it.** `is_email_verified` is written at
   `service.py:93` and never read by any authorization logic.
4. **No mail is sent in production.** `SENDGRID_API_KEY` is absent from the
   deploy's `--set-secrets` (`infra/gcp/cloudbuild.yaml:133`), so
   `senders.dispatch("EMAIL", ...)` takes the log-only branch at
   `senders.py:85`.

Gap 3 is intentional and stays (see Non-goals). Gaps 1 and 2 are this work.
Gap 4 is a credential task, documented here but not performed.

## Decisions

- **Advisory only.** No action anywhere on the platform is blocked by an
  unverified address. A broken mail pipeline must never be able to lock a real
  customer out of an account they already created.
- **Persistent, non-dismissible banner.** With zero enforcement, a dismissible
  advisory is close to no advisory at all — the users most likely to dismiss it
  are exactly the ones who will never verify.
- **No post-register interstitial.** `RegisterPage.tsx:49-54` already
  auto-logs-in and navigates home, so a global banner is on screen immediately
  after signup. An interstitial would add a route and a redirect branch to buy
  what the banner gives for free, and would leave returning unverified users
  with no reminder.
- **Mail dispatch stays in the router.** `forgot_password` and
  `request_email_verification` both mint the token in the service and dispatch
  from the router. Register follows the same split rather than introducing a
  second pattern.

## Design

### 1. Backend — send on register

`src/modules/users/router.py`

Add a module logger (the file currently has none; mirror
`senders.py:9,14`):

```python
import logging

logger = logging.getLogger(__name__)
```

Extract the dispatch block currently inlined in `request_email_verification`
into one helper, so the message copy and TTL wording have a single home:

```python
async def _send_verification_email(redis, user: User) -> str:
    """Mint a verification token and mail the link. Returns the token."""
    token = await service.request_email_verification(redis, user)
    link = _link("/verify-email", token)
    await senders.dispatch(
        "EMAIL", user.email,
        f"Confirm your email address: {link}\n\n"
        f"The link expires in {settings.email_verification_ttl_seconds // 3600} hours.",
        subject="Verify your email address",
    )
    return token
```

Rewrite `request_email_verification` to call it (behaviour unchanged, including
the non-production `debug_token`).

Extend `register`:

```python
user = await service.register_user(session, data)
# Best-effort: the account is already committed, so a Redis blip or a mail
# provider timeout must not turn a successful signup into a 500. The user can
# resend from the verification banner.
try:
    await _send_verification_email(redis, user)
except Exception:
    logger.warning(
        "Verification email failed for user %s", user.id, exc_info=True
    )
return user
```

The broad `except` is deliberate and is the one place in this change where it is
correct; the comment above it carries that reasoning into the code.

No new rate limit — `register` already throttles per IP at `router.py:56`.

### 2. Frontend — shared resend logic + global banner

**`frontend/src/auth/useEmailVerification.ts`** *(new)*
Hook exposing `{ send, busy, msg }`. This is the logic currently inlined in
`VerificationNotice`, lifted out unchanged.

**`frontend/src/components/VerificationBanner.tsx`** *(new)*
Slim strip. Returns `null` when `!user || user.is_email_verified`. Renders the
address, a **Resend** button, and inline success/error feedback from the hook.

**`frontend/src/components/AppShell.tsx`** *(edit)*
Mount `<VerificationBanner />` between `</header>` and `<Outlet />` (line 64),
inside `.app-content`, so it spans every authenticated page.

**`frontend/src/pages/account/VerificationNotice.tsx`** *(edit)*
Keep the Account-page card presentation; back it with the hook. Resend
behaviour is then defined exactly once.

### 3. Frontend — fix the stale-user bug

`VerifyEmailPage` confirms the token and reports success but never refreshes the
cached user, so `is_email_verified` stays `false` in `AuthContext` and the new
banner would persist after a successful verification until a hard reload.

`AuthContext` already exposes `refreshUser` (`AuthContext.tsx:16`). Call it after
a successful confirm. The page is reachable signed out, where `refreshUser`
clears to `null` and is harmless.

This is a pre-existing bug that only becomes user-visible once the banner
exists, so it is in scope.

## Testing

Extend `tests/modules/users/test_email_verification.py`, reusing its existing
`sent` fixture (which monkeypatches `users_router.senders.dispatch`).

**Existing test that must be updated:**
`test_request_emails_a_verification_link` asserts `len(sent) == 1` after
`_signed_in()` (which registers) plus one explicit request. Once register also
sends, that count becomes 2 and the test fails. Change it to `len(sent) == 2`
and assert the field checks against `sent[-1]` (the explicitly requested mail),
keeping its original intent — that an explicit request emails a link — intact.

**New tests:**

- registering dispatches exactly one `EMAIL` to the new address, whose body
  contains `/verify-email?token=`
- the token from the registration email verifies the account end-to-end.
  Registration returns `UserResponse`, which carries no `debug_token`, so the
  test parses the token out of the captured mail body — the same path a real
  user takes. A small module-level helper in the test file
  (`_token_from(mail)`) keeps that parsing in one place.
- **registration still returns 201 when the mail transport raises** — patch
  `dispatch` to throw and assert the account is created and usable. This is the
  most important test in the set; it pins the best-effort guarantee.
- a duplicate-email registration (409) dispatches nothing

Frontend build must stay green: `cd frontend && npm run build`.
Backend lint must stay clean: `flake8 src`.

## Non-goals

- No gating of login, checkout, or any other action on `is_email_verified`.
- No new endpoints, no schema change, no Alembic migration — the column and both
  routes already exist.
- No change to the OTP / phone verification flow.
- Configuring SendGrid credentials (see below) is a separate operational task.

## Going live (not part of this change)

Until these exist, `dispatch("EMAIL", ...)` logs instead of sending, and the
link appears in Cloud Run logs rather than an inbox. The banner will truthfully
say a link was sent; it will not be delivered externally.

```bash
printf %s "$SENDGRID_KEY"  | gcloud secrets create SENDGRID_API_KEY    --data-file=- --project=food-project-poc
printf %s "$FROM_ADDRESS"  | gcloud secrets create SENDGRID_FROM_EMAIL --data-file=- --project=food-project-poc
```

Then append to `--set-secrets` in `infra/gcp/cloudbuild.yaml:133`:

```
,SENDGRID_API_KEY=SENDGRID_API_KEY:latest,SENDGRID_FROM_EMAIL=SENDGRID_FROM_EMAIL:latest
```

`senders.py` imports `sendgrid` lazily inside a `try`, so the dependency must
also be installed in the API image for the real transport to engage.

## Files touched

| File | Change |
|---|---|
| `src/modules/users/router.py` | logger, `_send_verification_email` helper, send on register |
| `frontend/src/auth/useEmailVerification.ts` | new — shared resend hook |
| `frontend/src/components/VerificationBanner.tsx` | new — global banner |
| `frontend/src/components/AppShell.tsx` | mount the banner |
| `frontend/src/pages/account/VerificationNotice.tsx` | use the shared hook |
| `frontend/src/pages/VerifyEmailPage.tsx` | `refreshUser()` after confirm |
| `tests/modules/users/test_email_verification.py` | update 1 test, add 4 |
