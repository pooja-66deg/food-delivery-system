"""Admin panel endpoints (admin-only)."""
import pytest


async def _login(api_client, role, email, phone):
    await api_client.post("/auth/register", json={"email": email, "phone": phone,
        "first_name": "T", "last_name": "U", "password": "supersecret1", "role": role})
    tok = (await api_client.post("/auth/login", json={"email": email, "password": "supersecret1"})).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


async def _make_admin(api_client, app_session, email="admin@x.com", phone="+15550000000"):
    """Register a user then promote to admin directly (no self-service admin)."""
    from sqlalchemy import select
    from src.modules.users.models import User

    await _login(api_client, "customer", email, phone)
    user = await app_session.scalar(select(User).where(User.email == email))
    user.role = "admin"
    await app_session.commit()
    tok = (await api_client.post("/auth/login", json={"email": email, "password": "supersecret1"})).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.mark.asyncio
async def test_admin_endpoints_forbidden_for_non_admin(api_client):
    cust = await _login(api_client, "customer", "c@x.com", "+15551110001")
    assert (await api_client.get("/admin/stats", headers=cust)).status_code == 403
    assert (await api_client.get("/admin/users", headers=cust)).status_code == 403
    assert (await api_client.get("/admin/orders", headers=cust)).status_code == 403


@pytest.mark.asyncio
async def test_admin_stats_and_listings(api_client, app_session):
    admin = await _make_admin(api_client, app_session)
    # a couple more users so counts are non-trivial
    await _login(api_client, "restaurant", "o@x.com", "+15551110002")
    await _login(api_client, "customer", "c2@x.com", "+15551110003")

    stats = (await api_client.get("/admin/stats", headers=admin)).json()
    assert stats["users"] >= 3
    assert "orders_by_status" in stats
    assert "gross_merchandise_value" in stats

    users = (await api_client.get("/admin/users", headers=admin)).json()
    assert any(u["email"] == "admin@x.com" and u["role"] == "admin" for u in users)

    orders = (await api_client.get("/admin/orders", headers=admin)).json()
    assert isinstance(orders, list)


@pytest.mark.asyncio
async def test_admin_can_run_timeout_sweep(api_client, app_session):
    admin = await _make_admin(api_client, app_session)
    resp = await api_client.post("/admin/expire-acceptances", headers=admin)
    assert resp.status_code == 200
    assert "expired" in resp.json()


@pytest.mark.asyncio
async def test_admin_requires_auth(api_client):
    assert (await api_client.get("/admin/stats")).status_code == 401
