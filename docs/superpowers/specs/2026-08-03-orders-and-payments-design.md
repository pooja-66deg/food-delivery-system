# Design — Orders tab & Stripe card payments

Date: 2026-08-03
Branch: `feat/orders-and-payments`
Phase: F (see `2026-07-31-auth-forms-and-role-routing-design.md`)
Status: approved, implementing

## Problem

| Item | State before this branch |
| --- | --- |
| Orders tab | `OrdersPage` is one flat list. No active/past split, no way to act on an order that is waiting for payment. |
| Card payments | The provider abstraction and a `StripeProvider` exist, but nothing uses them properly. |
| Webhooks | Absent. |

And a defect: `create_order_from_checkout` advances **every** order to
`PAYMENT_SUCCESS` with the reason "COD: to be collected", regardless of method.
A CARD order is therefore marked paid before any money moves, the restaurant is
told to cook it, and the customer is never charged.

## Decisions

- **A card order is not a paid order.** CARD stops at `PAYMENT_PENDING` until a
  webhook says otherwise. COD keeps today's authorize-on-placement behaviour.
- **The restaurant never sees an unpaid order.** The kitchen must not start
  cooking something nobody has paid for.
- **Abandoned checkouts expire and give their stock back.** Phase E reserves
  stock at order creation; without an expiry sweep an abandoned card checkout
  holds that reservation forever.
- **Signature verification is implemented directly, not via the SDK.** Stripe's
  scheme is a documented HMAC; writing it out makes it real security *and*
  testable in an environment with no Stripe credentials.
- **Stripe.js is added to the frontend**, with the honest caveat recorded under
  Testing below.

## Backend

### Provider layer

`ProviderResult` gains `client_secret`. `StripeProvider.authorize` already
creates the PaymentIntent; it returns the secret alongside the id.
`create_payment_for_order` returns `PaymentSetup(payment, client_secret)` — the
secret reaches the client in the checkout response and is never persisted.

### Checkout

| Method | Flow |
| --- | --- |
| COD | Unchanged: `CREATED → PAYMENT_PENDING → PAYMENT_SUCCESS`, "to be collected". |
| CARD, Stripe configured | `CREATED → PAYMENT_PENDING`, stop. The response carries `payment_client_secret`. The webhook completes it. |
| CARD, no `STRIPE_SECRET_KEY` | The existing deterministic stand-in authorizes inline and the order completes at checkout, exactly as today. No dev-only endpoint; the response simply carries no secret. |

`OrderRead` gains `payment_client_secret: str | None`, set transiently on the
checkout response only.

### Webhook — `POST /payments/webhook`

`src/modules/payments/webhook.py` holds the two concerns:

- `verify_signature(payload: bytes, header: str, secret: str, now, tolerance)` —
  parses `t=…,v1=…`, recomputes `HMAC-SHA256(f"{t}.{payload}")`, compares in
  constant time, and rejects a timestamp outside the tolerance window (default
  300s) so a captured request cannot be replayed later.
- `handle_event(session, redis, event)` — dispatches on `type`.

| Event | Effect |
| --- | --- |
| `payment_intent.succeeded` | Payment → `SUCCEEDED`, order → `PAYMENT_SUCCESS`, restaurant notified (the existing `_emit_status` path). |
| `payment_intent.payment_failed` | Payment → `FAILED`. The order stays `PAYMENT_PENDING` so the customer can retry until it expires. |
| anything else | Ignored, 200. Stripe retries anything that is not 2xx. |

Idempotent twice over: a Redis guard keyed on the event id (7-day TTL), and a
state check that makes reprocessing a no-op even if the guard is lost. A bad or
missing signature is 400. The order is located by `Payment.provider_ref`
matching the PaymentIntent id.

### Unpaid expiry

`expire_unpaid_orders(session, now)` cancels `PAYMENT_PENDING` orders older than
`payment_window_seconds` (default 900) through the same SYSTEM cancel path the
acceptance sweep uses — which already restores stock and notifies the customer.
Exposed at `POST /orders/internal/expire-unpaid`, mirroring
`/orders/internal/expire-acceptances`.

### Resuming an abandoned payment

The checkout secret is never stored, so a customer who closed the tab has no way
back to it. `POST /payments/order/{id}/resume` mints a fresh PaymentIntent for
the same order and repoints the payment row at it; the abandoned intent expires
on its own. It returns the payment unchanged (no secret) when there is nothing
to pay — a settled order, or one that was never on card. `PaymentRead` carries
`client_secret`, populated only here.

### Listing

- `GET /orders?scope=active|past|all` (default `all`). Active is any status not
  in `DELIVERED`, `CANCELLED`, `REJECTED`. Filtering is server-side so
  pagination stays correct.
- `list_orders_for_restaurant` excludes `CREATED` and `PAYMENT_PENDING`.

### Config

`stripe_webhook_secret: str | None`, `payment_window_seconds: int = 900`,
`stripe_webhook_tolerance_seconds: int = 300`. All three in `.env.example`.

## Frontend

New `frontend/src/payments/`:

```
payments/
  StripeElements.tsx   loads the publishable key (once per key), wraps <Elements>
  CardPaymentStep.tsx  PaymentElement + confirmPayment(redirect: 'if_required')
  publishableKey.ts    reads VITE_STRIPE_PUBLISHABLE_KEY, null when unset
```

A `processing` intent counts as paid to the customer: the webhook settles it,
and blocking them on that screen would be a dead end.

The cart's checkout gains a COD/CARD choice. With no publishable key the card
option is hidden and COD is the only path, so the app runs with no Stripe
configuration at all. When checkout returns a `payment_client_secret`, the card
step opens; on success the customer lands on the order page, and on failure the
order stays payable.

`OrdersPage` gains Active / Past tabs backed by `?scope=`, and an order sitting
at `PAYMENT_PENDING` shows **Pay now**, which calls the resume endpoint above
and reopens the card step with the fresh secret.

`.env.example` gains `VITE_STRIPE_PUBLISHABLE_KEY` on the frontend and
`STRIPE_WEBHOOK_SECRET`, `STRIPE_WEBHOOK_TOLERANCE_SECONDS`, and
`PAYMENT_WINDOW_SECONDS` on the backend.

## Test plan

Written test-first per the repository TDD convention.

| Test | Asserts |
| --- | --- |
| `tests/modules/orders/test_card_checkout.py` | COD still completes at checkout; CARD stops at `PAYMENT_PENDING` and returns a secret when Stripe is configured; CARD without configuration completes inline; an unpaid order is hidden from the restaurant list and a paid one is not; resume returns a fresh secret, and nothing for a settled order |
| `tests/modules/payments/test_webhook.py` | A correctly signed `payment_intent.succeeded` advances the order and marks the payment; a bad signature is 400; a missing header is 400; a stale timestamp is 400; a replayed event changes nothing; `payment_intent.payment_failed` marks the payment failed and leaves the order pending; an unknown event type is accepted and ignored |
| `tests/modules/orders/test_unpaid_expiry.py` | An expired pending order is cancelled and its stock restored; a fresh one is left alone; a COD order is never swept |
| `tests/modules/orders/test_order_scope.py` | `scope=active` excludes delivered/cancelled/rejected; `scope=past` is the complement; the default returns everything |
| `frontend/tests/pages/OrdersPage.test.tsx` | Tabs request the right scope; a pending order offers Pay now; an empty tab shows its own message |
| `frontend/tests/payments/CardPaymentStep.test.tsx` | The client secret is passed to `confirmPayment`; success reports success; a declined card surfaces the Stripe message and leaves the order payable |

## Testing caveat

The Stripe card element cannot be exercised end to end here: there are no keys,
and the element renders in a cross-origin iframe no test can drive. Its tests
mock `@stripe/react-stripe-js` and assert *our* wiring — that the secret is
passed through, `confirmPayment` is called, and both outcomes are handled. The
webhook, the pending/paid state machine, the expiry sweep, and the orders tab
carry no such caveat and are tested for real.

## Verification

```bash
pytest                         # backend, must stay green
flake8 src                     # must stay clean
cd frontend && npm test        # vitest
cd frontend && npm run build   # tsc + vite
alembic upgrade head           # no new migration this phase
```

## Out of scope

- Saved cards and off-session charges.
- Partial refunds; refunds remain all-or-nothing.
- Apple Pay / Google Pay wallets (`PaymentElement` may surface them, but nothing
  is done to configure or test them).
- A scheduler for the expiry sweeps. Both remain admin-triggered endpoints, as
  the acceptance sweep already is — wiring a scheduler belongs with phase J.
