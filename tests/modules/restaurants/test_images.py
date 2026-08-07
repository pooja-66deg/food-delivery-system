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


# Test GCS storage (mocked)
from unittest.mock import MagicMock, patch, AsyncMock
from io import BytesIO
from src.core.exceptions import ValidationException


@patch("src.modules.restaurants.storage_gcs.settings")
@patch("src.modules.restaurants.storage_gcs.storage.Client")
async def test_save_image_gcs_valid_file(mock_client_class, mock_settings):
    # Mock settings
    mock_settings.gcs_bucket_name = "test-bucket"

    # Mock the GCS client
    mock_bucket = MagicMock()
    mock_blob = MagicMock()
    mock_bucket.blob.return_value = mock_blob
    mock_blob.public_url = "https://storage.googleapis.com/test-bucket/restaurants/1/abc123.jpg"

    mock_client = MagicMock()
    mock_client.bucket.return_value = mock_bucket
    mock_client_class.return_value = mock_client

    # Create a mock UploadFile with required attributes
    upload = MagicMock()
    upload.filename = "test.jpg"
    upload.content_type = "image/jpeg"
    upload.read = AsyncMock(return_value=b"fake image data")

    # Import here so the patch is active
    from src.modules.restaurants.storage_gcs import save_image_gcs

    # Call the function
    url = await save_image_gcs(upload, "restaurants/1")

    # Assert it returns a public URL
    assert url.startswith("https://storage.googleapis.com/test-bucket/")
    assert ".jpg" in url
    # Assert the client was called
    mock_client.bucket.assert_called_once_with("test-bucket")


@patch("src.modules.restaurants.storage_gcs.storage.Client")
async def test_save_image_gcs_invalid_type(mock_client_class):
    # Create a mock UploadFile with invalid content type
    upload = MagicMock()
    upload.filename = "test.txt"
    upload.content_type = "text/plain"
    upload.read = AsyncMock(return_value=b"not an image")

    from src.modules.restaurants.storage_gcs import save_image_gcs

    with pytest.raises(ValidationException, match="Unsupported image type"):
        await save_image_gcs(upload, "restaurants/1")


# Tests for routing logic (save_image)

@pytest.mark.asyncio
async def test_save_image_routes_to_local_in_dev(monkeypatch, tmp_path):
    """In development environment, save_image routes to local storage."""
    monkeypatch.setattr("src.modules.restaurants.storage.settings.environment", "development")
    monkeypatch.setattr("src.modules.restaurants.storage.settings.media_root", str(tmp_path))

    from src.modules.restaurants.storage import save_image

    upload = MagicMock()
    upload.filename = "test.jpg"
    upload.content_type = "image/jpeg"
    upload.read = AsyncMock(return_value=b"fake jpeg data")

    url = await save_image(upload, "test")

    # Should return a /media URL
    assert url.startswith("/media/test/")
    assert url.endswith(".jpg")


@pytest.mark.asyncio
@patch("src.modules.restaurants.storage_gcs.storage.Client")
async def test_save_image_routes_to_gcs_in_prod(mock_client_class, monkeypatch):
    """In production environment, save_image routes to GCS."""
    monkeypatch.setattr("src.modules.restaurants.storage.settings.environment", "production")

    mock_bucket = MagicMock()
    mock_blob = MagicMock()
    mock_bucket.blob.return_value = mock_blob
    mock_blob.public_url = "https://storage.googleapis.com/bucket/test/abc.jpg"
    mock_client = MagicMock()
    mock_client.bucket.return_value = mock_bucket
    mock_client_class.return_value = mock_client

    # Patch settings in storage_gcs module
    with patch("src.modules.restaurants.storage_gcs.settings") as mock_gcs_settings:
        mock_gcs_settings.gcs_bucket_name = "bucket"

        from src.modules.restaurants.storage import save_image

        upload = MagicMock()
        upload.filename = "test.jpg"
        upload.content_type = "image/jpeg"
        upload.read = AsyncMock(return_value=b"fake jpeg data")

        url = await save_image(upload, "restaurants/1")

        # Should return a GCS URL
        assert url.startswith("https://storage.googleapis.com/")
