"""One mailbox, one spelling.

``EmailStr`` lower-cases the domain and leaves the local part alone, which is
correct per RFC 5321 and wrong for every provider this platform serves. Every
lookup compared raw, so a capital anywhere in the local part meant:

- login refused with the right password, and
- forgot-password answering its deliberately-identical "a reset link has been
  sent" while minting no token — the anti-enumeration wording turning a
  functional failure into a silent one.

It also let one mailbox hold two accounts, since the unique constraint saw two
different strings.
"""

import pytest


async def _register(client, register_payload, **overrides):
    payload = {**register_payload(), **overrides}
    r = await client.post("/auth/register", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


class TestRegistrationStoresOneSpelling:
    async def test_capitals_are_folded_on_the_way_in(self, client, register_payload):
        body = await _register(
            client, register_payload, email="MiXeD.Case@Example.COM"
        )
        assert body["email"] == "mixed.case@example.com"

    async def test_surrounding_whitespace_is_stripped(self, client, register_payload):
        body = await _register(client, register_payload, email="  spaced@example.com  ")
        assert body["email"] == "spaced@example.com"

    async def test_a_case_variant_cannot_take_a_second_account(
        self, client, register_payload
    ):
        """The hole this closes: two rows, one mailbox, both satisfying the
        unique constraint because Postgres compares case-sensitively."""
        await _register(client, register_payload, email="owner@example.com")
        r = await client.post(
            "/auth/register",
            json={
                **register_payload(),
                "email": "Owner@Example.com",
                "phone": "+919876543299",
            },
        )
        assert r.status_code == 409, r.text


class TestLoginAcceptsAnyCasing:
    @pytest.mark.parametrize(
        "typed", ["user@example.com", "User@Example.com", "USER@EXAMPLE.COM", " user@example.com "]
    )
    async def test_the_owner_gets_in_however_they_type_it(
        self, client, register_payload, typed
    ):
        await _register(client, register_payload, email="user@example.com")
        r = await client.post(
            "/auth/login", json={"email": typed, "password": register_payload()["password"]}
        )
        assert r.status_code == 200, r.text
        assert r.json()["access_token"]

    async def test_a_genuinely_different_address_still_fails(
        self, client, register_payload
    ):
        """Folding must not make unrelated addresses equal."""
        await _register(client, register_payload, email="user@example.com")
        r = await client.post(
            "/auth/login",
            json={"email": "user2@example.com", "password": register_payload()["password"]},
        )
        assert r.status_code == 401


class TestPasswordRecoveryReachesTheOwner:
    async def test_a_case_variant_mints_a_token(self, client, register_payload):
        """Previously this returned the same reassuring 200 and did nothing, so
        the user waited for mail that was never sent."""
        await _register(client, register_payload, email="forgot@example.com")
        r = await client.post(
            "/auth/forgot-password", json={"email": "Forgot@Example.COM"}
        )
        assert r.status_code == 200, r.text
        # The dev-mode response carries the token; in production it is absent and
        # only the email has it. Its presence here is what proves one was issued.
        assert r.json().get("debug_token"), "no reset token was issued for a case variant"

    async def test_an_unknown_address_is_still_indistinguishable(
        self, client, register_payload
    ):
        """The anti-enumeration property has to survive the fix."""
        await _register(client, register_payload, email="known@example.com")
        known = await client.post("/auth/forgot-password", json={"email": "known@example.com"})
        unknown = await client.post("/auth/forgot-password", json={"email": "nobody@example.com"})
        assert known.status_code == unknown.status_code == 200
        assert set(known.json()) - {"debug_token"} == set(unknown.json()) - {"debug_token"}
