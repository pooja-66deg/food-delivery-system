"""Password hashing utilities.

Uses bcrypt directly (rather than passlib) so hashing works cleanly on modern
bcrypt releases without version-shim warnings. Note bcrypt's 72-byte input
limit; schema validation caps password length well under it.
"""

import bcrypt


def hash_password(password: str) -> str:
    """Return a bcrypt hash of the given plaintext password."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Return True if the plaintext password matches the stored hash."""
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
