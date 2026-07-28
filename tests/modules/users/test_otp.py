"""Tests for OTP request/verify against an in-memory Redis."""

import pytest

from src.config import settings
from src.core.exceptions import TooManyRequestsException, UnauthorizedException
from src.modules.users import otp


def _wrong_code(code: str) -> str:
    """Return a code of the same length guaranteed to differ from ``code``."""
    bumped = (int(code) + 1) % (10 ** len(code))
    return str(bumped).zfill(len(code))


@pytest.mark.asyncio
async def test_request_otp_stores_salted_hash_with_ttl(fake_redis):
    code = await otp.request_otp(fake_redis, "+15551110000")

    assert len(code) == settings.otp_length and code.isdigit()
    stored = await fake_redis.get("otp:code:+15551110000")
    assert stored is not None
    assert stored != code  # stored as a hash, never plaintext
    ttl = await fake_redis.ttl("otp:code:+15551110000")
    assert 0 < ttl <= settings.otp_expiration_seconds


@pytest.mark.asyncio
async def test_request_otp_rate_limited(fake_redis):
    phone = "+15551110001"
    for _ in range(settings.otp_request_max):
        await otp.request_otp(fake_redis, phone)

    with pytest.raises(TooManyRequestsException):
        await otp.request_otp(fake_redis, phone)


@pytest.mark.asyncio
async def test_verify_otp_success_consumes_code(fake_redis):
    phone = "+15551110002"
    code = await otp.request_otp(fake_redis, phone)

    assert await otp.verify_otp(fake_redis, phone, code) is True
    # A consumed code cannot be reused.
    assert await fake_redis.get(f"otp:code:{phone}") is None


@pytest.mark.asyncio
async def test_verify_otp_wrong_code_rejected(fake_redis):
    phone = "+15551110003"
    code = await otp.request_otp(fake_redis, phone)

    with pytest.raises(UnauthorizedException):
        await otp.verify_otp(fake_redis, phone, _wrong_code(code))


@pytest.mark.asyncio
async def test_verify_otp_locks_after_max_attempts(fake_redis):
    phone = "+15551110004"
    code = await otp.request_otp(fake_redis, phone)
    wrong = _wrong_code(code)

    for _ in range(settings.otp_max_attempts):
        with pytest.raises(UnauthorizedException):
            await otp.verify_otp(fake_redis, phone, wrong)

    # After exhausting attempts, even the correct code is refused.
    with pytest.raises(UnauthorizedException):
        await otp.verify_otp(fake_redis, phone, code)


@pytest.mark.asyncio
async def test_verify_otp_missing_code_rejected(fake_redis):
    with pytest.raises(UnauthorizedException):
        await otp.verify_otp(fake_redis, "+15559999999", "123456")
