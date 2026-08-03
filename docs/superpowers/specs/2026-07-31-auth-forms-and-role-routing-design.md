# Design — Auth forms & role-aware account page

Date: 2026-07-31
Branch: `fix/auth-forms-and-role-routing`
Status: awaiting review

## Programme context

A backlog of 24 reported bugs/features was de-duplicated into 10 groups. Each
group gets one branch and one PR, in this order:

| Phase | Branch | Covers |
| --- | --- | --- |
| A | `fix/auth-forms-and-role-routing` | Name/phone input filtering on profile, password show/hide, driver account page |
| C | `fix/manage-restaurants-layout` | "Your restaurants" card colliding with the page heading |
| B | `feat/search-and-discovery` | City/name search, restaurant typeahead, popular cuisines on empty state |
| D | `feat/account-and-sessions` | Address edit, email verification, change password, real reset email, full logout invalidation |
| E | `feat/merchant-catalog` | Category update/delete, menu item edit/delete, image display, inventory (stock, remaining qty, auto out-of-stock) |
| F | `feat/orders-and-payments` | Orders tab (active + past), Stripe card payments + webhooks |
| G | `feat/reviews-display` | Review display and rating aggregation on restaurant pages |
| H | `feat/delivery-tracking` | Google Maps live driver tracking and ETA |
| I | `feat/admin-and-analytics` | Remaining admin dashboard, advanced search, analytics, reporting |
| J | `chore/production-readiness` | Kafka event relay, Kubernetes, CI/CD, monitoring, logging, performance |

Infrastructure lands last so hardening does not chase a moving target.

**Prerequisite:** `feat/orders-module` must merge into `main` first. `main` is 8
commits behind and lacks the orders, reviews, notifications, and
payment-method work. All phase branches cut from `main` after that merge.

## Already resolved by the prerequisite merge

Two reported bugs are already fixed on `feat/orders-module` and were only
observed as broken because the running build came from `main`:

- **Names reject digits and specials.** `onlyLetters` filter in
  `frontend/src/pages/RegisterPage.tsx` plus `pattern="[A-Za-z ]+"`.
- **Phone accepts digits only.** `onlyPhone` filter, `inputMode="numeric"`,
  `pattern="\+?[0-9]+"`.
- Enforced server-side by `_validate_name` / `_validate_phone` in
  `src/modules/users/schemas.py`, applied to both `UserCreate` and
  `UserUpdate`, and covered by 8 cases in
  `tests/modules/users/test_register_validation.py`.

No new work. Verify after merging rather than reimplementing.

## Scope

### 1. Extract shared input filters

`onlyLetters` and `onlyPhone` are inline local functions in `RegisterPage`.
Move them to `frontend/src/lib/inputFilters.ts` and export as pure functions so
the register and profile forms share one definition.

Rules must mirror the backend exactly:

- `filterNameInput` — keep `A-Za-z` and space. Spaces are retained so
  multi-word given names work; the backend already accepts them.
- `filterPhoneInput` — keep digits, allow a single leading `+`, strip `+`
  anywhere else.

Pure string-to-string functions with no React dependency, so they are trivially
testable and reusable by later phases.

### 2. `PasswordField` component

Add to `frontend/src/components/ui.tsx`, alongside the existing `Field`.

- Wraps `Field`, toggling `type` between `password` and `text`.
- Toggle is `<button type="button">` so it can never submit the form.
- `aria-label` alternates "Show password" / "Hide password"; `aria-pressed`
  reflects current state.
- Default state is masked.

Applied to all three password inputs: `LoginPage`, `RegisterPage`,
`ResetPasswordPage`.

### 3. Profile form parity

`ProfilePanel` in `AccountPage` uses plain `set()` handlers for `first_name`,
`last_name`, and `phone`, so invalid input is only rejected by the server on
save and surfaces as a raw API error. Switch to the shared filters plus
`pattern` / `title`, matching the register form. This closes a UX gap, not a
security hole — the server already rejects the input.

### 4. Role-aware account page

`AccountPage` renders one layout for every role. Two defects:

- The chip ternary handles `restaurant` and `admin`, so `driver` falls through
  to "Customer account".
- `AddressPanel` ("Delivery addresses") renders for all roles, including
  drivers and restaurant owners who have no use for customer delivery
  addresses.

Changes:

- Derive the chip label from role, including `driver` → "Driver account".
- Render `AddressPanel` only when role is `customer`.
- Rewrite the subtitle so it does not promise "delivery addresses" to roles
  that do not see that panel.

Role gating is a single derived value in `AccountPage`, not scattered
conditionals, so later phases can extend it without touching the panels.

### 5. Frontend test harness

No frontend test framework exists — no vitest, no jest, no testing-library, no
test files. `npm run build` runs `tsc` only.

Add as part of this branch:

- `vitest`, `@testing-library/react`, `@testing-library/jest-dom`,
  `@testing-library/user-event`, `jsdom` as devDependencies.
- A `test` block in the existing `vite.config.ts` (using `defineConfig` from
  `vitest/config`) rather than a separate `vitest.config.ts`, so the React
  plugin is not duplicated.
- `"test": "vitest run"` and `"test:watch": "vitest"` scripts.

Tests live in `frontend/tests/`, mirroring the `src/` layout — the same
source/test split the backend already uses with `tests/modules/<domain>/`.
`src/` stays production code only.

```
frontend/
  src/lib/inputFilters.ts
  src/components/ui.tsx
  tests/setup.ts
  tests/lib/inputFilters.test.ts
  tests/components/ui.test.tsx
  tests/pages/AccountPage.test.tsx
  tests/pages/RegisterPage.test.tsx
  tests/pages/passwordReveal.test.tsx
```

`tsconfig.json` includes `tests` so `tsc` typechecks them during
`npm run build`; Vitest's `include` is scoped to `tests/**/*.test.{ts,tsx}`.

Every later frontend phase inherits this harness.

### 6. Unanchored `lib/` ignore rule

The root `.gitignore` inherited `lib/` from the Python packaging template.
Unanchored, that pattern matches at any depth, so `frontend/src/lib/` was
ignored and `inputFilters.ts` would have been absent from the commit — the
build would pass locally and fail everywhere else.

Anchor the Python packaging rules to the repo root: `lib/` → `/lib/`,
`lib64/` → `/lib64/`.

## Test plan

Written test-first per the repository TDD convention.

| Test | Asserts |
| --- | --- |
| `inputFilters.test.ts` | `filterNameInput` strips digits and specials, keeps spaces; `filterPhoneInput` keeps digits, allows one leading `+`, strips interior `+` |
| `ui.test.tsx` | `PasswordField` starts masked; clicking the toggle switches to text and back; `aria-label` and `aria-pressed` update; toggle does not submit its form |
| `AccountPage.test.tsx` | Chip reads "Driver account" for driver, "Customer account" for customer, "Restaurant account" for restaurant, "Admin account" for admin; `AddressPanel` renders for customer only |
| `AccountPage.test.tsx` | Typing `Alex1` into first name yields `Alex`; typing `call-me` into phone yields empty |

Backend is untouched, so `pytest` must stay green as a regression check.

## Out of scope

- Register-form name/phone validation — already implemented and tested; arrives
  with the prerequisite merge.
- Driver vehicle, licence, availability, and delivery stats — phase H.
- Address **editing**. `AddressPanel` has add and delete but no update, and
  `src/modules/users/profile.py` has no `update_address`. A real gap, deferred
  to phase D.
- Password strength rules beyond the existing 8-character minimum.

## Verification

```bash
cd frontend && npm test        # new vitest suite
cd frontend && npm run build   # tsc typecheck + vite build
pytest                         # backend regression, must stay green
flake8 src                     # must stay clean
```

Manual check: sign in as a driver, open the Account tab, confirm the chip reads
"Driver account" and no delivery-address panel appears.

## Risks

- Adding vitest touches `package.json` and `package-lock.json`, which will
  conflict with any other branch that changes dependencies. Mitigated by
  landing this branch first.
- `PasswordField` replaces inputs on three pages; a missed `autoComplete`
  attribute would degrade password-manager behaviour. The component forwards
  all props through to `Field` to prevent this.
