"""Card checkout must not mark an order paid before money moves."""

from decimal import Decimal

import pytest

from src.modules.orders.models import OrderStatus, PaymentStatus
from src.modules.payments import service as payment_service
from src.modules.payments.providers import ProviderResult


class _StripeLike:
    """Stands in for a configured Stripe: hands back a client secret and waits
    for the webhook rather than settling inline."""

    name = "CARD"

    async def authorize(self, amount: Decimal, idempotency_key: str) -> ProviderResult:
        return ProviderResult(
            ok=True, reference="pi_test_123", status="requires_confirmation",
            client_secret="pi_test_123_secret_abc",
        )

    async def refund(self, reference, amount) -> ProviderResult:
        return ProviderResult(ok=True, reference=reference, status="refunded")


@pytest.fixture
def stripe_configured(monkeypatch):
    """Route CARD payments through a provider that behaves like real Stripe."""
    monkeypatch.setattr(
        payment_service, "provider_for",
        lambda method: _StripeLike() if method == "CARD" else payment_service.provider_for(method),
    )


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
    assert resp.json()["payment_client_secret"] is None


@pytest.mark.asyncio
async def test_card_order_waits_for_payment(api_client, stripe_configured):
    _, _, cust, body = await _seed_cart(api_client)

    resp = await api_client.post("/orders/checkout", headers=cust,
                                 json={**body, "payment_method": "CARD"})

    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == OrderStatus.PAYMENT_PENDING.value
    assert resp.json()["payment_status"] == PaymentStatus.PENDING.value


@pytest.mark.asyncio
async def test_card_checkout_returns_the_client_secret(api_client, stripe_configured):
    _, _, cust, body = await _seed_cart(api_client)

    resp = await api_client.post("/orders/checkout", headers=cust,
                                 json={**body, "payment_method": "CARD"})

    assert resp.json()["payment_client_secret"] == "pi_test_123_secret_abc"


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
    assert resp.json()["payment_client_secret"] is None


@pytest.mark.asyncio
async def test_resume_gives_a_customer_their_payment_back(api_client, stripe_configured):
    """The checkout secret is never stored, so someone who closed the tab needs
    a fresh one to finish paying."""
    _, _, cust, body = await _seed_cart(api_client)
    order = (await api_client.post("/orders/checkout", headers=cust,
                                   json={**body, "payment_method": "CARD"})).json()

    resumed = await api_client.post(f"/payments/order/{order['id']}/resume", headers=cust)

    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["client_secret"] == "pi_test_123_secret_abc"


@pytest.mark.asyncio
async def test_resume_offers_nothing_on_a_settled_order(api_client):
    _, _, cust, body = await _seed_cart(api_client)
    order = (await api_client.post("/orders/checkout", headers=cust,
                                   json={**body, "payment_method": "COD"})).json()

    resumed = await api_client.post(f"/payments/order/{order['id']}/resume", headers=cust)

    assert resumed.status_code == 200
    assert resumed.json()["client_secret"] is None


@pytest.mark.asyncio
async def test_card_order_records_the_payment_intent(api_client, stripe_configured):
    _, _, cust, body = await _seed_cart(api_client)

    order = (await api_client.post("/orders/checkout", headers=cust,
                                   json={**body, "payment_method": "CARD"})).json()

    payment = (await api_client.get(f"/payments/order/{order['id']}", headers=cust)).json()
    assert payment["provider"] == "CARD"
    assert payment["provider_ref"] == "pi_test_123"
