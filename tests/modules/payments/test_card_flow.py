"""Online CARD payment method through checkout (Stripe stub when no keys)."""
import pytest

from src.modules.payments.providers import CardProvider, StripeProvider, provider_for


async def _login(api_client, role, email, phone):
    await api_client.post("/auth/register", json={"email": email, "phone": phone,
        "first_name": "T", "last_name": "U", "password": "supersecret1", "role": role})
    tok = (await api_client.post("/auth/login", json={"email": email, "password": "supersecret1"})).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def test_provider_for_card_uses_stub_without_stripe_key(monkeypatch):
    from src.config import settings
    monkeypatch.setattr(settings, "stripe_secret_key", None)
    assert isinstance(provider_for("CARD"), CardProvider)


def test_provider_for_card_uses_stripe_when_configured(monkeypatch):
    from src.config import settings
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_123")
    assert isinstance(provider_for("CARD"), StripeProvider)


@pytest.mark.asyncio
async def test_checkout_with_card_records_card_payment(api_client):
    owner = await _login(api_client, "restaurant", "o@x.com", "+15559520001")
    rid = (await api_client.post("/restaurants", json={"name": "P", "city": "Metropolis",
        "address_line": "1", "phone": "+15550000000", "min_order_amount": "5.00"}, headers=owner)).json()["id"]
    await api_client.patch(f"/restaurants/{rid}", json={"is_open": True}, headers=owner)
    cat = (await api_client.post(f"/restaurants/{rid}/categories", json={"name": "M"}, headers=owner)).json()
    item = (await api_client.post(f"/restaurants/{rid}/items",
        json={"category_id": cat["id"], "name": "Pizza", "price": "10.00"}, headers=owner)).json()
    cust = await _login(api_client, "customer", "c@x.com", "+15559520002")
    await api_client.post("/cart/items", json={"menu_item_id": item["id"], "quantity": 1}, headers=cust)
    await api_client.post("/users/me/addresses",
        json={"label": "h", "line1": "1", "city": "Metropolis", "postal_code": "1"}, headers=cust)
    addr = (await api_client.get("/users/me/addresses", headers=cust)).json()[0]["id"]
    ph = (await api_client.get("/cart", headers=cust)).json()["price_hash"]

    order = (await api_client.post("/orders/checkout",
        json={"address_id": addr, "price_hash": ph, "payment_method": "CARD"}, headers=cust)).json()
    assert order["payment_method"] == "CARD"

    payment = (await api_client.get(f"/payments/order/{order['id']}", headers=cust)).json()
    assert payment["provider"] == "CARD"
    assert payment["status"] == "AUTHORIZED"
