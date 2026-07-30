"""Restaurant + menu-item image upload (local media store)."""
import pytest

from src.config import settings

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32  # minimal PNG-ish payload


async def _owner(api_client):
    await api_client.post("/auth/register", json={"email": "o@x.com", "phone": "+15559710001",
        "first_name": "O", "last_name": "W", "password": "supersecret1", "role": "restaurant"})
    tok = (await api_client.post("/auth/login", json={"email": "o@x.com", "password": "supersecret1"})).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.mark.asyncio
async def test_upload_restaurant_and_item_images(api_client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "media_root", str(tmp_path))
    owner = await _owner(api_client)
    rid = (await api_client.post("/restaurants", json={"name": "P", "city": "Metropolis",
        "address_line": "1", "phone": "+15550000000", "min_order_amount": "5.00"}, headers=owner)).json()["id"]

    # restaurant image
    r = await api_client.post(f"/restaurants/{rid}/image",
        files={"file": ("logo.png", _PNG, "image/png")}, headers=owner)
    assert r.status_code == 200, r.text
    assert r.json()["image_url"].startswith(f"/media/restaurants/{rid}/")

    # menu-item image
    cat = (await api_client.post(f"/restaurants/{rid}/categories", json={"name": "M"}, headers=owner)).json()
    item = (await api_client.post(f"/restaurants/{rid}/items",
        json={"category_id": cat["id"], "name": "Pizza", "price": "10.00"}, headers=owner)).json()
    ri = await api_client.post(f"/restaurants/{rid}/items/{item['id']}/image",
        files={"file": ("pizza.png", _PNG, "image/png")}, headers=owner)
    assert ri.status_code == 200, ri.text
    assert ri.json()["image_url"].startswith(f"/media/restaurants/{rid}/items/")


@pytest.mark.asyncio
async def test_rejects_non_image(api_client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "media_root", str(tmp_path))
    owner = await _owner(api_client)
    rid = (await api_client.post("/restaurants", json={"name": "P", "city": "Metropolis",
        "address_line": "1", "phone": "+15550000000", "min_order_amount": "5.00"}, headers=owner)).json()["id"]
    bad = await api_client.post(f"/restaurants/{rid}/image",
        files={"file": ("notes.txt", b"hello", "text/plain")}, headers=owner)
    assert bad.status_code == 422
