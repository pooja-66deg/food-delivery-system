"""OTP generation and verification backed by Redis.

Codes are never stored in plaintext: a per-code random salt plus a SHA-256 hash
is cached with a short TTL. Requests are rate-limited per phone number and
verification attempts are capped.
"""

import hashlib
import secrets

from redis.asyncio import Redis

from app.config import settings
from shared.errors import TooManyRequestsException, UnauthorizedException

_CODE_KEY = "otp:code:{phone}"
_ATTEMPTS_KEY = "otp:attempts:{phone}"
_REQUEST_KEY = "otp:req:{phone}"


def _hash(salt: str, phone: str, code: str) -> str:
    return hashlib.sha256(f"{salt}:{phone}:{code}".encode("utf-8")).hexdigest()


def _generate_code() -> str:
    return str(secrets.randbelow(10 ** settings.otp_length)).zfill(settings.otp_length)


async def request_otp(redis: Redis, phone: str) -> str:
    """Generate a fresh OTP for ``phone``, cache its salted hash, and return the
    plaintext code for dispatch (e.g. SMS). Rate-limited per phone number.
    """
    request_key = _REQUEST_KEY.format(phone=phone)
    count = await redis.incr(request_key)
    if count == 1:
        await redis.expire(request_key, settings.otp_request_window_seconds)
    if count > settings.otp_request_max:
        raise TooManyRequestsException("Too many OTP requests. Please try again later.")

    code = _generate_code()
    salt = secrets.token_hex(8)
    await redis.set(
        _CODE_KEY.format(phone=phone),
        f"{salt}${_hash(salt, phone, code)}",
        ex=settings.otp_expiration_seconds,
    )
    await redis.delete(_ATTEMPTS_KEY.format(phone=phone))
    return code


async def verify_otp(redis: Redis, phone: str, code: str) -> bool:
    """Validate ``code`` for ``phone``.

    Returns True on success (and consumes the code). Raises UnauthorizedException
    if the code is missing/expired, incorrect, or the attempt cap is exceeded.
    """
    code_key = _CODE_KEY.format(phone=phone)
    stored = await redis.get(code_key)
    if stored is None:
        raise UnauthorizedException("OTP expired or not requested")

    attempts_key = _ATTEMPTS_KEY.format(phone=phone)
    attempts = await redis.incr(attempts_key)
    await redis.expire(attempts_key, settings.otp_expiration_seconds)
    if attempts > settings.otp_max_attempts:
        await redis.delete(code_key, attempts_key)
        raise UnauthorizedException("Too many invalid attempts")

    salt, _, expected = stored.partition("$")
    if _hash(salt, phone, code) != expected:
        raise UnauthorizedException("Invalid OTP")

    await redis.delete(code_key, attempts_key)
    return True
