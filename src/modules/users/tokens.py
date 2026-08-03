"""Single-use tokens backed by Redis.

Password reset and email verification both hand the user an opaque token that
must be redeemable exactly once. Only the SHA-256 hash is stored, so a Redis
dump never yields a usable token, and the key is deleted as it is read so two
concurrent redemptions cannot both succeed.
"""

import hashlib
import secrets


def _key(prefix: str, token: str) -> str:
    return f"{prefix}:{hashlib.sha256(token.encode('utf-8')).hexdigest()}"


async def issue_single_use(redis, prefix: str, user_id: int, ttl_seconds: int) -> str:
    """Mint a token for ``user_id``, storing its hash under ``prefix``."""
    token = secrets.token_urlsafe(32)
    await redis.set(_key(prefix, token), str(user_id), ex=ttl_seconds)
    return token


async def consume_single_use(redis, prefix: str, token: str) -> int | None:
    """Redeem ``token``, returning the user id, or None if it is unknown,
    expired, or already spent."""
    user_id = await redis.getdel(_key(prefix, token))
    return None if user_id is None else int(user_id)
