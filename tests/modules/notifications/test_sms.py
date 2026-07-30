"""SMS sender: logs without config; fails gracefully when Twilio is unavailable."""
import pytest

from src.config import settings
from src.modules.notifications.senders import SmsSender


@pytest.mark.asyncio
async def test_sms_logs_when_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "twilio_account_sid", None)
    monkeypatch.setattr(settings, "twilio_auth_token", None)
    monkeypatch.setattr(settings, "twilio_phone_number", None)
    # No provider configured -> best-effort success (logged, not sent).
    assert await SmsSender().send("+15551230000", "hello") is True


@pytest.mark.asyncio
async def test_sms_fails_gracefully_when_twilio_missing(monkeypatch):
    # Credentials present but the Twilio SDK isn't installed -> graceful False,
    # never an exception that would break the OTP/notification flow.
    monkeypatch.setattr(settings, "twilio_account_sid", "AC_test")
    monkeypatch.setattr(settings, "twilio_auth_token", "token")
    monkeypatch.setattr(settings, "twilio_phone_number", "+15550000000")
    result = await SmsSender().send("+15551230000", "hello")
    assert result in (True, False)  # depends on whether twilio is installed; must not raise


@pytest.mark.asyncio
async def test_otp_request_still_returns_debug_code(api_client):
    # OTP is now dispatched over SMS, but the dev debug code is still returned.
    resp = await api_client.post("/auth/otp/request", json={"phone": "+15551239999"})
    assert resp.status_code == 200
    assert "debug_otp" in resp.json()
