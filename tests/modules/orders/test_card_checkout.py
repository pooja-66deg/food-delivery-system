"""Card checkout must not mark an order paid before money moves."""

from decimal import Decimal

import pytest

from src.modules.orders.models import OrderStatus, PaymentStatus
from src.modules.payments import service as payment_service
from src.modules.payments.providers import ProviderResult


CHECKOUT_URL = "https://checkout.stripe.com/c/pay/cs_test_123"


class _StripeLike:
    """Stands in for a configured Stripe: hands back a hosted checkout URL and
    waits to be told the money moved rather than settling inline.

    ``paid`` is what Stripe would report when the session is looked up, so a
    test can decide whether the customer actually went through with it.
    """

    name = "CARD"

    def __init__(self, paid: bool = False):
        self.paid = paid

    async def authorize(
        self, amount: Decimal, idempotency_key: str, order_id: int
    ) -> ProviderResult:
        return ProviderResult(
            ok=True, reference="cs_test_123", status="open", checkout_url=CHECKOUT_URL,
        )

    async def verify(self, reference) -> ProviderResult:
        return ProviderResult(
            ok=self.paid,
            reference="pi_test_123" if self.paid else reference,
            status="paid" if self.paid else "unpaid",
        )

    async def refund(self, reference, amount) -> ProviderResult:
        return ProviderResult(ok=True, reference=reference, status="refunded")


def _route_card_to(monkeypatch, provider):
    monkeypatch.setattr(
        payment_service, "provider_for",
        lambda method: provider if method == "CARD" else payment_service.provider_for(method),
    )


@pytest.fixture
def stripe_configured(monkeypatch):
    """Route CARD payments through a provider that behaves like real Stripe."""
    _route_card_to(monkeypatch, _StripeLike())


@pytest.fixture
def stripe_paid(monkeypatch):
    """As above, but Stripe reports the session as paid when looked up."""
    _route_card_to(monkeypatch, _StripeLike(paid=True))


async def _seed_cart(api_client, suffix="1"):
    await api_client.post("/auth/register", json={
        "email": f"cardowner{suffix}@x.com", "phone": f"+1555930000{suffix}",
        "first_name": "O", "last_name": "W", "password": "supersecret1", "role": "restaurant"})
    owner = {"Authorization": "Bearer " + (await api_client.post("/auth/login", json={
        "email": f"cardowner{suffix}@x.com", "password": "supersecret1"})).json()["access_token"]}

    rid = (await api_client.post("/restaurants", headers=owner, json={
        "name": "Card Cafe", "city": "Metropolis", "address_line": "1 Main St",
        "phone": "+15550000000"})).json()["id"]
    await api_client.patch(f"/restaurants/{rid}", headers=owner, json={"is_open": True})
    cat = (await api_client.post(f"/restaurants/{rid}/categories", headers=owner,
                                 json={"name": "Mains"})).json()
    item = (await api_client.post(f"/restaurants/{rid}/items", headers=owner, json={
        "category_id": cat["id"], "name": "Pizza", "price": "10.00"})).json()

    await api_client.post("/auth/register", json={
        "email": f"cardcust{suffix}@x.com", "phone": f"+1555931000{suffix}",
        "first_name": "C", "last_name": "U", "password": "supersecret1", "role": "customer"})
    cust = {"Authorization": "Bearer " + (await api_client.post("/auth/login", json={
        "email": f"cardcust{suffix}@x.com", "password": "supersecret1"})).json()["access_token"]}
    await api_client.post("/cart/items", headers=cust,
                          json={"menu_item_id": item["id"], "quantity": 1})
    await api_client.post("/users/me/addresses", headers=cust, json={
        "label": "home", "line1": "1 Main St", "city": "Metropolis", "postal_code": "12345"})
    addr = (await api_client.get("/users/me/addresses", headers=cust)).json()[0]["id"]
    price_hash = (await api_client.get("/cart", headers=cust)).json()["price_hash"]
    return owner, rid, cust, {"address_id": addr, "price_hash": price_hash}


@pytest.mark.asyncio
async def test_cod_still_completes_at_checkout(api_client):
    _, _, cust, body = await _seed_cart(api_client)

    resp = await api_client.post("/orders/checkout", headers=cust,
                                 json={**body, "payment_method": "COD"})

    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == OrderStatus.PAYMENT_SUCCESS.value
    assert resp.json()["payment_status"] == PaymentStatus.SUCCESS.value
    assert resp.json()["payment_checkout_url"] is None


@pytest.mark.asyncio
async def test_card_order_waits_for_payment(api_client, stripe_configured):
    _, _, cust, body = await _seed_cart(api_client)

    resp = await api_client.post("/orders/checkout", headers=cust,
                                 json={**body, "payment_method": "CARD"})

    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == OrderStatus.PAYMENT_PENDING.value
    assert resp.json()["payment_status"] == PaymentStatus.PENDING.value


@pytest.mark.asyncio
async def test_card_checkout_returns_the_checkout_url(api_client, stripe_configured):
    _, _, cust, body = await _seed_cart(api_client)

    resp = await api_client.post("/orders/checkout", headers=cust,
                                 json={**body, "payment_method": "CARD"})

    assert resp.json()["payment_checkout_url"] == CHECKOUT_URL


@pytest.mark.asyncio
async def test_unpaid_card_order_is_hidden_from_the_restaurant(api_client, stripe_configured):
    """The kitchen must not start cooking something nobody has paid for."""
    owner, rid, cust, body = await _seed_cart(api_client)

    await api_client.post("/orders/checkout", headers=cust,
                          json={**body, "payment_method": "CARD"})

    listed = await api_client.get(f"/orders/restaurant/{rid}", headers=owner)
    assert listed.json() == []


@pytest.mark.asyncio
async def test_paid_order_reaches_the_restaurant(api_client):
    owner, rid, cust, body = await _seed_cart(api_client)

    await api_client.post("/orders/checkout", headers=cust,
                          json={**body, "payment_method": "COD"})

    listed = await api_client.get(f"/orders/restaurant/{rid}", headers=owner)
    assert len(listed.json()) == 1


@pytest.mark.asyncio
async def test_card_without_stripe_configured_completes_inline(api_client):
    """With no secret key the deterministic stand-in settles at checkout, so
    local development needs no Stripe at all."""
    _, _, cust, body = await _seed_cart(api_client)

    resp = await api_client.post("/orders/checkout", headers=cust,
                                 json={**body, "payment_method": "CARD"})

    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == OrderStatus.PAYMENT_SUCCESS.value
    assert resp.json()["payment_checkout_url"] is None


@pytest.mark.asyncio
async def test_resume_gives_a_customer_their_payment_back(api_client, stripe_configured):
    """The checkout URL is never stored, so someone who closed the tab needs a
    fresh one to finish paying."""
    _, _, cust, body = await _seed_cart(api_client)
    order = (await api_client.post("/orders/checkout", headers=cust,
                                   json={**body, "payment_method": "CARD"})).json()

    resumed = await api_client.post(f"/payments/order/{order['id']}/resume", headers=cust)

    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["checkout_url"] == CHECKOUT_URL


@pytest.mark.asyncio
async def test_resume_offers_nothing_on_a_settled_order(api_client):
    _, _, cust, body = await _seed_cart(api_client)
    order = (await api_client.post("/orders/checkout", headers=cust,
                                   json={**body, "payment_method": "COD"})).json()

    resumed = await api_client.post(f"/payments/order/{order['id']}/resume", headers=cust)

    assert resumed.status_code == 200
    assert resumed.json()["checkout_url"] is None


@pytest.mark.asyncio
async def test_card_order_records_the_checkout_session(api_client, stripe_configured):
    _, _, cust, body = await _seed_cart(api_client)

    order = (await api_client.post("/orders/checkout", headers=cust,
                                   json={**body, "payment_method": "CARD"})).json()

    payment = (await api_client.get(f"/payments/order/{order['id']}", headers=cust)).json()
    assert payment["provider"] == "CARD"
    assert payment["provider_ref"] == "cs_test_123"


@pytest.mark.asyncio
async def test_confirm_settles_an_order_stripe_reports_as_paid(api_client, stripe_paid):
    """The return leg from the hosted page settles the order, so a setup with no
    webhook tunnel — every local one — still works."""
    _, _, cust, body = await _seed_cart(api_client)
    order = (await api_client.post("/orders/checkout", headers=cust,
                                   json={**body, "payment_method": "CARD"})).json()
    assert order["status"] == OrderStatus.PAYMENT_PENDING.value

    confirmed = await api_client.post(f"/payments/order/{order['id']}/confirm", headers=cust)

    assert confirmed.status_code == 200, confirmed.text
    reloaded = (await api_client.get(f"/orders/{order['id']}", headers=cust)).json()
    assert reloaded["status"] == OrderStatus.PAYMENT_SUCCESS.value
    assert reloaded["payment_status"] == PaymentStatus.SUCCESS.value


@pytest.mark.asyncio
async def test_confirm_records_the_intent_for_refunds(api_client, stripe_paid):
    _, _, cust, body = await _seed_cart(api_client)
    order = (await api_client.post("/orders/checkout", headers=cust,
                                   json={**body, "payment_method": "CARD"})).json()

    confirmed = (await api_client.post(
        f"/payments/order/{order['id']}/confirm", headers=cust)).json()

    assert confirmed["provider_ref"] == "pi_test_123"
    assert confirmed["status"] == "SUCCEEDED"


@pytest.mark.asyncio
async def test_confirm_does_not_settle_an_unpaid_order(api_client, stripe_configured):
    """Visiting the success URL without paying must not mark anything paid —
    the redirect is a hint, Stripe's own answer is the authority."""
    _, _, cust, body = await _seed_cart(api_client)
    order = (await api_client.post("/orders/checkout", headers=cust,
                                   json={**body, "payment_method": "CARD"})).json()

    confirmed = await api_client.post(f"/payments/order/{order['id']}/confirm", headers=cust)

    assert confirmed.status_code == 200
    reloaded = (await api_client.get(f"/orders/{order['id']}", headers=cust)).json()
    assert reloaded["status"] == OrderStatus.PAYMENT_PENDING.value


@pytest.mark.asyncio
async def test_confirming_twice_settles_once(api_client, stripe_paid):
    """The webhook and the return leg both fire in production."""
    _, _, cust, body = await _seed_cart(api_client)
    order = (await api_client.post("/orders/checkout", headers=cust,
                                   json={**body, "payment_method": "CARD"})).json()

    await api_client.post(f"/payments/order/{order['id']}/confirm", headers=cust)
    second = await api_client.post(f"/payments/order/{order['id']}/confirm", headers=cust)

    assert second.status_code == 200
    reloaded = (await api_client.get(f"/orders/{order['id']}", headers=cust)).json()
    paid = [e for e in reloaded["events"] if e["to_status"] == OrderStatus.PAYMENT_SUCCESS.value]
    assert len(paid) == 1


@pytest.mark.asyncio
async def test_confirm_is_a_no_op_on_a_cod_order(api_client):
    _, _, cust, body = await _seed_cart(api_client)
    order = (await api_client.post("/orders/checkout", headers=cust,
                                   json={**body, "payment_method": "COD"})).json()

    confirmed = await api_client.post(f"/payments/order/{order['id']}/confirm", headers=cust)

    assert confirmed.status_code == 200
    assert confirmed.json()["provider"] == "COD"


@pytest.mark.asyncio
async def test_confirm_refuses_someone_elses_order(api_client, stripe_paid):
    _, _, cust, body = await _seed_cart(api_client)
    order = (await api_client.post("/orders/checkout", headers=cust,
                                   json={**body, "payment_method": "CARD"})).json()
    _, _, stranger, _ = await _seed_cart(api_client, suffix="2")

    confirmed = await api_client.post(f"/payments/order/{order['id']}/confirm", headers=stranger)

    assert confirmed.status_code in (403, 404)
