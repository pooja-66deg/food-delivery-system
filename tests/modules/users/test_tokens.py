"""Tests for the single-use token helper shared by reset and verification."""
import pytest

from src.modules.users import tokens


@pytest.mark.asyncio
async def test_issue_then_consume_returns_the_user_id(fake_redis):
    token = await tokens.issue_single_use(fake_redis, "test", 42, 60)
    assert await tokens.consume_single_use(fake_redis, "test", token) == 42


@pytest.mark.asyncio
async def test_token_cannot_be_used_twice(fake_redis):
    token = await tokens.issue_single_use(fake_redis, "test", 42, 60)
    await tokens.consume_single_use(fake_redis, "test", token)
    assert await tokens.consume_single_use(fake_redis, "test", token) is None


@pytest.mark.asyncio
async def test_unknown_token_returns_none(fake_redis):
    assert await tokens.consume_single_use(fake_redis, "test", "never-issued") is None


@pytest.mark.asyncio
async def test_prefixes_are_isolated(fake_redis):
    """A verification token must not be redeemable as a reset token."""
    token = await tokens.issue_single_use(fake_redis, "verify", 42, 60)
    assert await tokens.consume_single_use(fake_redis, "reset", token) is None


@pytest.mark.asyncio
async def test_plaintext_token_is_never_stored(fake_redis):
    token = await tokens.issue_single_use(fake_redis, "test", 7, 60)
    keys = await fake_redis.keys("test:*")
    assert keys and all(token not in key for key in keys)
