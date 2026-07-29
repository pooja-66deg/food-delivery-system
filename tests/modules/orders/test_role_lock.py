"""Cart + customer-order endpoints are restricted to the customer role."""
import pytest


async def _login(api_client, role, email, phone):
    await api_client.post("/auth/register", json={"email": email, "phone": phone,
        "first_name": "T", "last_name": "U", "password": "supersecret1", "role": role})
    tok = (await api_client.post("/auth/login", json={"email": email, "password": "supersecret1"})).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.mark.asyncio
async def test_non_customer_cannot_use_cart_or_checkout(api_client):
    owner = await _login(api_client, "restaurant", "o@x.com", "+15551230001")
    driver = await _login(api_client, "driver", "d@x.com", "+15551230002")

    for headers in (owner, driver):
        assert (await api_client.get("/cart", headers=headers)).status_code == 403
        assert (await api_client.post("/cart/items", json={"menu_item_id": 1, "quantity": 1},
                                      headers=headers)).status_code == 403
        assert (await api_client.post("/orders/checkout", json={"address_id": 1, "price_hash": "x"},
                                      headers=headers)).status_code == 403
        assert (await api_client.get("/orders", headers=headers)).status_code == 403


@pytest.mark.asyncio
async def test_customer_still_allowed(api_client):
    cust = await _login(api_client, "customer", "c@x.com", "+15551230003")
    assert (await api_client.get("/cart", headers=cust)).status_code == 200
    assert (await api_client.get("/orders", headers=cust)).status_code == 200
