"""Payment capture, failure, retry, and history."""
from decimal import Decimal

import pytest

from src.modules.orders.models import Order, OrderStatus
from src.modules.payments import service
from src.modules.payments.models import PaymentTxStatus
from src.modules.payments.providers import ProviderResult


class _FailingProvider:
    name = "CARD"

    async def authorize(self, amount, idempotency_key, order_id):
        return ProviderResult(ok=False, reference=None, status="declined")

    async def refund(self, reference, amount):
        return ProviderResult(ok=True, status="refunded")


class _RecoveringProvider:
    name = "CARD"

    async def authorize(self, amount, idempotency_key, order_id):
        return ProviderResult(ok=True, reference="pi_ok", status="authorized")

    async def refund(self, reference, amount):
        return ProviderResult(ok=True, status="refunded")


async def _order(session, total="20.00", method="CARD"):
    order = Order(customer_id=1, restaurant_id=1, address_id=1,
                  status=OrderStatus.PAYMENT_SUCCESS.value, payment_method=method,
                  subtotal=Decimal(total), total=Decimal(total))
    session.add(order)
    await session.commit()
    await session.refresh(order)
    return order


@pytest.mark.asyncio
async def test_capture_moves_to_succeeded(db_session):
    order = await _order(db_session, method="COD")
    await service.create_payment_for_order(db_session, order)
    captured = await service.capture_payment(db_session, order)
    assert captured.status == PaymentTxStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_failed_authorization_marks_failed(db_session):
    order = await _order(db_session)
    payment = await service.create_payment_for_order(db_session, order, provider=_FailingProvider())
    assert payment.status == PaymentTxStatus.FAILED


@pytest.mark.asyncio
async def test_retry_recovers_failed_payment(db_session):
    order = await _order(db_session)
    await service.create_payment_for_order(db_session, order, provider=_FailingProvider())
    retried = await service.retry_payment(db_session, order, provider=_RecoveringProvider())
    assert retried.status == PaymentTxStatus.AUTHORIZED
    assert retried.provider_ref == "pi_ok"


@pytest.mark.asyncio
async def test_retry_noop_when_not_failed(db_session):
    order = await _order(db_session, method="COD")
    await service.create_payment_for_order(db_session, order)  # AUTHORIZED
    same = await service.retry_payment(db_session, order)
    assert same.status == PaymentTxStatus.AUTHORIZED


@pytest.mark.asyncio
async def test_payment_history_endpoint(api_client):
    # place a COD order as a customer, then list payment history
    await api_client.post("/auth/register", json={"email": "o@x.com", "phone": "+15559510001",
        "first_name": "O", "last_name": "W", "password": "supersecret1", "role": "restaurant"})
    owner = {"Authorization": "Bearer " + (await api_client.post("/auth/login",
        json={"email": "o@x.com", "password": "supersecret1"})).json()["access_token"]}
    rid = (await api_client.post("/restaurants", json={"name": "P", "city": "Metropolis",
        "address_line": "1", "phone": "+15550000000", "min_order_amount": "5.00"}, headers=owner)).json()["id"]
    await api_client.patch(f"/restaurants/{rid}", json={"is_open": True}, headers=owner)
    cat = (await api_client.post(f"/restaurants/{rid}/categories", json={"name": "M"}, headers=owner)).json()
    item = (await api_client.post(f"/restaurants/{rid}/items",
        json={"category_id": cat["id"], "name": "Pizza", "price": "10.00"}, headers=owner)).json()
    await api_client.post("/auth/register", json={"email": "c@x.com", "phone": "+15559510002",
        "first_name": "C", "last_name": "U", "password": "supersecret1", "role": "customer"})
    cust = {"Authorization": "Bearer " + (await api_client.post("/auth/login",
        json={"email": "c@x.com", "password": "supersecret1"})).json()["access_token"]}
    await api_client.post("/cart/items", json={"menu_item_id": item["id"], "quantity": 1}, headers=cust)
    await api_client.post("/users/me/addresses",
        json={"label": "h", "line1": "1", "city": "Metropolis", "postal_code": "1"}, headers=cust)
    addr = (await api_client.get("/users/me/addresses", headers=cust)).json()[0]["id"]
    ph = (await api_client.get("/cart", headers=cust)).json()["price_hash"]
    await api_client.post("/orders/checkout", json={"address_id": addr, "price_hash": ph}, headers=cust)

    history = await api_client.get("/payments", headers=cust)
    assert history.status_code == 200
    assert len(history.json()) == 1
    assert history.json()[0]["provider"] == "COD"
