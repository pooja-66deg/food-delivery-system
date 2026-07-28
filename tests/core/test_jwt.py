"""Tests for JWT creation and verification."""

from datetime import timedelta

import pytest

from src.core.exceptions import UnauthorizedException
from src.core.jwt import create_access_token, verify_token


def test_verify_returns_claims_for_valid_token():
    token = create_access_token({"sub": "42", "role": "customer"})

    payload = verify_token(token)

    assert payload["sub"] == "42"
    assert payload["role"] == "customer"


def test_verify_rejects_tampered_token():
    token = create_access_token({"sub": "42"})

    with pytest.raises(UnauthorizedException):
        verify_token(token + "tampered")


def test_verify_rejects_expired_token():
    token = create_access_token({"sub": "42"}, expires_delta=timedelta(seconds=-1))

    with pytest.raises(UnauthorizedException):
        verify_token(token)
