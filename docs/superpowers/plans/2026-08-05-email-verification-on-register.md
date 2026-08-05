# Email Verification on Registration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mail a verification link when a user registers, and surface an app-wide advisory prompt until the address is confirmed.

**Architecture:** The verification endpoints, Redis token store, `is_email_verified` column and `/verify-email` page all already exist. This work wires the missing trigger (send on register), surfaces the prompt app-wide via a banner in `AppShell`, and de-duplicates the resend logic into one hook shared by the banner and the existing Account-page card. Token minting stays in the service layer and mail dispatch stays in the router, matching `forgot_password` and `request_email_verification`.

**Tech Stack:** FastAPI (async), SQLAlchemy 2.0, Redis (fakeredis in tests), pytest + pytest-asyncio, React 18 + TypeScript + Vite.

**Spec:** `docs/superpowers/specs/2026-08-05-email-verification-on-register-design.md`

## Global Constraints

- **Advisory only.** Nothing may be gated on `is_email_verified`. Do not add any check that blocks login, checkout, or any other action.
- **No schema change.** The `users.is_email_verified` column already exists. Do **not** create an Alembic migration.
- **No new endpoints.** `POST /auth/verify-email/request` and `/confirm` already exist and are unchanged in behaviour.
- **`flake8 src` must stay clean.**
- **`cd frontend && npm run build` must stay green** (this runs `tsc` typecheck then `vite build`).
- **Mail is log-only in this environment.** `SENDGRID_API_KEY` is not configured, so `senders.dispatch("EMAIL", ...)` logs instead of sending. Do not describe this feature as delivering email externally.
- **Git steps are for the human.** This repo's `CLAUDE.md` reserves all `git add` / `git commit` / branch operations for the human operator. Commit steps below are written as suggested commands for the human to run — an AI worker must not execute them, and must not add a `Co-Authored-By:` trailer.
- Branch: `feat/email-verification-on-register`.

---

### Task 1: Backend — send the verification email on register

**Files:**
- Modify: `src/modules/users/router.py` (add logger; extract helper from lines 125-145; extend `register` at lines 51-60)
- Test: `tests/modules/users/test_email_verification.py`

**Interfaces:**
- Consumes: `service.register_user(session, data) -> User`, `service.request_email_verification(redis, user) -> str`, `senders.dispatch(channel, to, message, subject=None) -> bool`, `_link(path, token) -> str` — all already exist.
- Produces: `_send_verification_email(redis, user) -> str` — a module-private helper in `router.py`. No later task imports it.

- [ ] **Step 1: Update the existing test that this change breaks**

`test_request_emails_a_verification_link` currently asserts `len(sent) == 1`. Its `_signed_in()` helper registers first, so once registration also sends mail the count becomes 2 and the test fails. Change the count and read the fields off the last mail:

```python
@pytest.mark.asyncio
async def test_request_emails_a_verification_link(api_client, sent):
    headers = await _signed_in(api_client)
    await api_client.post("/auth/verify-email/request", headers=headers)

    # Two now: one from registration, one from the explicit request.
    assert len(sent) == 2
    mail = sent[-1]
    assert mail["channel"] == "EMAIL"
    assert mail["to"] == EMAIL
    assert "/verify-email?token=" in mail["message"]
    assert mail["subject"] and "Order update" not in mail["subject"]
```

- [ ] **Step 2: Add a token-parsing helper and the new failing tests**

Add near `_signed_in` at the top of the file:

```python
def _token_from(mail) -> str:
    """Pull the verification token out of an emailed link.

    Registration returns UserResponse, which carries no debug_token, so tests
    read the token the same way a real user does — out of the message body.
    """
    return mail["message"].split("/verify-email?token=")[1].split()[0]
```

Append these four tests:

```python
@pytest.mark.asyncio
async def test_registering_emails_a_verification_link(api_client, sent):
    assert (await _register(api_client)).status_code == 201

    assert len(sent) == 1
    mail = sent[0]
    assert mail["channel"] == "EMAIL"
    assert mail["to"] == EMAIL
    assert "/verify-email?token=" in mail["message"]


@pytest.mark.asyncio
async def test_token_from_the_registration_email_verifies_the_account(api_client, sent):
    await _register(api_client)
    token = _token_from(sent[0])

    assert (await api_client.post(
        "/auth/verify-email/confirm", json={"token": token})).status_code == 204

    tokens = (await api_client.post(
        "/auth/login", json={"email": EMAIL, "password": PASSWORD})).json()
    me = (await api_client.get("/users/me", headers={
        "Authorization": f"Bearer {tokens['access_token']}"})).json()
    assert me["is_email_verified"] is True


@pytest.mark.asyncio
async def test_register_succeeds_when_the_mail_transport_fails(api_client, monkeypatch):
    """The account is committed before the email is attempted, so a provider
    outage must not turn a successful signup into a 500."""
    async def _boom(channel, to, message, subject=None):
        raise RuntimeError("mail provider down")

    monkeypatch.setattr(users_router.senders, "dispatch", _boom)

    assert (await _register(api_client)).status_code == 201

    login = await api_client.post(
        "/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert login.status_code == 200


@pytest.mark.asyncio
async def test_a_duplicate_registration_sends_no_email(api_client, sent):
    await _register(api_client)
    sent.clear()

    assert (await _register(api_client)).status_code == 409
    assert sent == []
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `pytest tests/modules/users/test_email_verification.py -v --no-cov`

Expected: the four new tests FAIL (`assert 0 == 1` / `IndexError` on the token split, because registration sends nothing yet), and `test_request_emails_a_verification_link` FAILS on `assert 1 == 2`.

- [ ] **Step 4: Add a module logger to the router**

In `src/modules/users/router.py`, add to the imports at the top of the file:

```python
import logging
```

and after the import block, before `def _client_ip`:

```python
logger = logging.getLogger(__name__)
```

- [ ] **Step 5: Extract the mail-dispatch helper**

Add after `_link` in `src/modules/users/router.py`:

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

Then rewrite the body of `request_email_verification` (currently lines 125-145) to use it. Behaviour, including the non-production `debug_token`, is unchanged:

```python
@auth_router.post("/verify-email/request", status_code=status.HTTP_202_ACCEPTED)
async def request_email_verification(
    current_user: User = Depends(get_current_user), redis=Depends(get_redis),
):
    await enforce_rate_limit(
        redis, f"rl:verify:{current_user.id}",
        settings.auth_rate_max, settings.auth_rate_window_seconds,
    )
    token = await _send_verification_email(redis, current_user)
    body = {"message": "Verification email sent."}
    # Convenience for local/dev and tests; never exposed in production.
    if settings.environment != "production":
        body["debug_token"] = token
    return body
```

- [ ] **Step 6: Send on register**

Replace the body of `register` (currently lines 51-60) with:

```python
@auth_router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    data: UserRegister, request: Request,
    session: AsyncSession = Depends(get_db), redis=Depends(get_redis),
):
    await enforce_rate_limit(
        redis, f"rl:register:{_client_ip(request)}",
        settings.auth_rate_max, settings.auth_rate_window_seconds,
    )
    user = await service.register_user(session, data)
    # Best-effort. The account is already committed, so a Redis blip or a mail
    # provider timeout must not turn a successful signup into a 500 — the user
    # can resend from the verification banner.
    try:
        await _send_verification_email(redis, user)
    except Exception:
        logger.warning(
            "Verification email failed for user %s", user.id, exc_info=True
        )
    return user
```

The broad `except` is deliberate here and nowhere else in this change; the comment above it carries that reasoning.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `pytest tests/modules/users/test_email_verification.py -v --no-cov`
Expected: PASS, all tests in the file.

- [ ] **Step 8: Run the wider suite and lint**

Run: `pytest tests/modules/users -q --no-cov` then `flake8 src`

Expected: all pass, flake8 silent. If another users test asserts on a captured-mail count, update it the same way as Step 1 — registration now emits one extra `EMAIL`.

- [ ] **Step 9: Commit** *(human runs this)*

```bash
git add src/modules/users/router.py tests/modules/users/test_email_verification.py
git commit -m "feat: email a verification link when a user registers"
```

---

### Task 2: Frontend — extract the shared resend hook

Pure refactor. No behaviour change, no visual change. Kept separate so the banner in Task 4 reviews as new UI rather than UI plus a refactor.

**Files:**
- Create: `frontend/src/auth/useEmailVerification.ts`
- Modify: `frontend/src/pages/account/VerificationNotice.tsx`

**Interfaces:**
- Consumes: `useAuth()` from `frontend/src/auth/AuthContext.tsx` (provides `user`), `authApi.requestEmailVerification()` from `frontend/src/api/auth.ts`, `errorMessage(err, fallback)` from `frontend/src/api/client.ts`.
- Produces: `useEmailVerification(): { send: () => void; busy: boolean; msg: VerificationMessage | null }` and `type VerificationMessage = { kind: 'ok' | 'error'; text: string }`. **Task 4 depends on these exact names.**

- [ ] **Step 1: Create the hook**

Create `frontend/src/auth/useEmailVerification.ts`. This is the logic currently inlined in `VerificationNotice`, lifted out unchanged:

```ts
import { useState } from 'react'

import { authApi } from '../api/auth'
import { errorMessage } from '../api/client'
import { useAuth } from './AuthContext'

export type VerificationMessage = { kind: 'ok' | 'error'; text: string }

/**
 * Resend state for the email-verification prompts. Two places offer a resend —
 * the app-wide banner and the Account page card — so the request, the busy flag
 * and the user-facing copy live here instead of being duplicated in both.
 */
export function useEmailVerification() {
  const { user } = useAuth()
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<VerificationMessage | null>(null)

  const send = () => {
    setBusy(true)
    setMsg(null)
    void (async () => {
      try {
        await authApi.requestEmailVerification()
        setMsg({
          kind: 'ok',
          text: `Verification link sent to ${user?.email ?? 'your address'}.`,
        })
      } catch (err) {
        setMsg({
          kind: 'error',
          text: errorMessage(err, 'Could not send the verification email.'),
        })
      } finally {
        setBusy(false)
      }
    })()
  }

  return { send, busy, msg }
}
```

- [ ] **Step 2: Point VerificationNotice at the hook**

Replace the whole of `frontend/src/pages/account/VerificationNotice.tsx` with:

```tsx
import { useAuth } from '../../auth/AuthContext'
import { useEmailVerification } from '../../auth/useEmailVerification'
import { Alert, Button } from '../../components/ui'

/**
 * Advisory only — nothing on the platform is gated on a verified address, so
 * this informs rather than blocks. Registration already mails a link; this is
 * the Account-page resend, sharing its logic with the app-wide banner.
 */
export function VerificationNotice() {
  const { user } = useAuth()
  const { send, busy, msg } = useEmailVerification()

  if (!user) return null

  if (user.is_email_verified) {
    return (
      <p className="muted" style={{ marginBottom: '1.25rem' }}>
        <span className="chip chip-accent">Email verified</span>
      </p>
    )
  }

  return (
    <section className="card panel" style={{ marginBottom: '1.25rem' }}>
      <h3>Verify your email</h3>
      <p className="muted">
        <strong>{user.email}</strong> has not been confirmed yet. Verifying it lets us reach you
        about your orders.
      </p>
      {msg && <Alert kind={msg.kind}>{msg.text}</Alert>}
      <div style={{ marginTop: '1rem' }}>
        <Button type="button" onClick={send} loading={busy}>
          Send verification email
        </Button>
      </div>
    </section>
  )
}
```

- [ ] **Step 3: Verify the build**

Run: `cd frontend && npm run build`
Expected: `tsc` reports no errors and the vite build succeeds.

- [ ] **Step 4: Commit** *(human runs this)*

```bash
git add frontend/src/auth/useEmailVerification.ts frontend/src/pages/account/VerificationNotice.tsx
git commit -m "refactor: extract shared email-verification resend hook"
```

---

### Task 3: Frontend — refresh the cached user after verifying

Pre-existing bug. `VerifyEmailPage` confirms the token and reports success but never refreshes the cached user, so `is_email_verified` stays `false` in `AuthContext`. Fixing it before Task 4 means the banner never ships in a state where it persists after a successful verification.

**Files:**
- Modify: `frontend/src/pages/VerifyEmailPage.tsx`

**Interfaces:**
- Consumes: `useAuth()` → `refreshUser: () => Promise<void>`, already declared at `frontend/src/auth/AuthContext.tsx:16`.
- Produces: nothing importable.

- [ ] **Step 1: Add the refresh call**

In `frontend/src/pages/VerifyEmailPage.tsx`, add the import:

```tsx
import { useAuth } from '../auth/AuthContext'
```

Inside the component, above the existing `const [params] = useSearchParams()`:

```tsx
const { refreshUser } = useAuth()
```

Then in the `useEffect`, change the success branch from:

```tsx
        await authApi.confirmEmailVerification(token)
        setStatus('done')
```

to:

```tsx
        await authApi.confirmEmailVerification(token)
        // Drop the stale is_email_verified=false in AuthContext so the advisory
        // banner clears without a reload. No-op when opened signed out.
        await refreshUser()
        setStatus('done')
```

Add `refreshUser` to the effect's dependency array, so it reads `}, [token, refreshUser])`. `refreshUser` is wrapped in `useCallback` (`AuthContext.tsx:31`) so this does not re-run on every render, and the `attempted` ref guards against a second token spend regardless.

- [ ] **Step 2: Verify the build**

Run: `cd frontend && npm run build`
Expected: no `tsc` errors, build succeeds.

- [ ] **Step 3: Commit** *(human runs this)*

```bash
git add frontend/src/pages/VerifyEmailPage.tsx
git commit -m "fix: refresh cached user after email verification"
```

---

### Task 4: Frontend — app-wide verification banner

**Files:**
- Create: `frontend/src/components/VerificationBanner.tsx`
- Modify: `frontend/src/components/AppShell.tsx` (mount between `</header>` at line 64 and `<Outlet />` at line 65)
- Modify: `frontend/src/layout.css` (append the banner styles)

**Interfaces:**
- Consumes: `useEmailVerification()` from Task 2 (`{ send, busy, msg }`), `useAuth()` → `user`, `Button` from `frontend/src/components/ui`.
- Produces: `VerificationBanner` — a named export with no props.

- [ ] **Step 1: Create the banner component**

Create `frontend/src/components/VerificationBanner.tsx`:

```tsx
import { useAuth } from '../auth/AuthContext'
import { useEmailVerification } from '../auth/useEmailVerification'
import { Button } from './ui'

/**
 * App-wide advisory. Registration mails a verification link, but nothing on the
 * platform is gated on a verified address, so this nudges without blocking.
 * Renders nothing once the address is confirmed, or when signed out.
 */
export function VerificationBanner() {
  const { user } = useAuth()
  const { send, busy, msg } = useEmailVerification()

  if (!user || user.is_email_verified) return null

  return (
    <div className="verify-banner" role="status">
      <span className="verify-banner-text">
        Confirm <strong>{user.email}</strong> so we can reach you about your orders.
      </span>
      {msg && <span className={`verify-banner-msg ${msg.kind}`}>{msg.text}</span>}
      <Button type="button" variant="ghost" onClick={send} loading={busy}>
        Resend link
      </Button>
    </div>
  )
}
```

- [ ] **Step 2: Mount it in AppShell**

In `frontend/src/components/AppShell.tsx`, add to the local imports (after the `BrandMark` import on line 6):

```tsx
import { VerificationBanner } from './VerificationBanner'
```

Then insert the component between the closing `</header>` and `<Outlet />`:

```tsx
        </header>
        <VerificationBanner />
        <Outlet />
```

- [ ] **Step 3: Add the styles**

Append to `frontend/src/layout.css`:

```css
/* Email-verification advisory — an app-wide strip under the topbar. Saffron
   rather than --danger: an unconfirmed address is a nudge, not an error. The
   1.75rem side margin lines it up with .topbar's horizontal padding. */
.verify-banner {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.75rem;
  margin: 1rem 1.75rem 0;
  padding: 0.7rem 1rem;
  border: 1px solid var(--line);
  border-left: 3px solid var(--saffron);
  border-radius: var(--r-md);
  background: var(--paper);
  box-shadow: var(--shadow-sm);
  font-size: 0.92rem;
  color: var(--ink);
}
.verify-banner-text {
  flex: 1;
  min-width: 12rem;
}
.verify-banner-msg {
  color: var(--ink-soft);
}
.verify-banner-msg.error {
  color: var(--danger);
}

@media (max-width: 820px) {
  .verify-banner {
    margin: 0.75rem 1rem 0;
  }
}
```

- [ ] **Step 4: Verify the build**

Run: `cd frontend && npm run build`
Expected: no `tsc` errors, build succeeds.

- [ ] **Step 5: Check it in the running app**

Run `docker compose up --build`, then at http://localhost:5173 register a fresh account. Confirm:
1. The banner appears immediately after registration (`RegisterPage` auto-logs-in, so no navigation is needed to see it).
2. It shows on more than one page — click through to Restaurants and Orders.
3. **Resend link** produces the success message.
4. The backend log shows a `[notify:EMAIL] (no provider)` line containing a `/verify-email?token=…` link — this is the expected log-only transport, not a failure.
5. Opening that link verifies the account, and the banner disappears **without** a manual reload (this is Task 3 working).
6. The Account page shows the "Email verified" chip.

Eyeball the banner's alignment against the topbar and page content; adjust the `margin` in Step 3 if it looks off.

- [ ] **Step 6: Commit** *(human runs this)*

```bash
git add frontend/src/components/VerificationBanner.tsx frontend/src/components/AppShell.tsx frontend/src/layout.css
git commit -m "feat: app-wide email verification banner"
```

---

## Final verification

- [ ] `pytest -m "not integration"` — full backend suite green
- [ ] `flake8 src` — silent
- [ ] `cd frontend && npm run build` — green
- [ ] Manual walkthrough from Task 4 Step 5 completed

## Out of scope

Configuring SendGrid so mail actually leaves the system. Until `SENDGRID_API_KEY` and `SENDGRID_FROM_EMAIL` exist in Secret Manager and are added to `--set-secrets` in `infra/gcp/cloudbuild.yaml:133`, the link only reaches the logs. Commands are in the spec's "Going live" section.
