"""Registration, approval, and what each role may see and do.

The rules under test are the ones a reader would otherwise have to reconstruct
from three modules:

- an owner registers their own venue, and gets exactly one;
- a registered venue is invisible to customers until an operator approves it;
- an owner can still see their own unapproved venue, or they cannot tell a
  pending registration from a lost one;
- only an operator decides, and an operator cannot register a venue at all.
"""

from app.models import APPROVED, PENDING, REJECTED

VENUE = {
    "name": "Tiffin House",
    "city": "Surat",
    "address_line": "1 KK Road",
    "phone": "+919876500001",
}


async def _register(client, auth, user_id=7, **overrides):
    return await client.post(
        "/restaurants", json={**VENUE, **overrides}, headers=auth(user_id, "restaurant")
    )


async def test_a_new_restaurant_starts_pending(client, auth):
    r = await _register(client, auth)
    assert r.status_code == 201, r.text
    assert r.json()["approval_status"] == PENDING


async def test_an_owner_cannot_approve_their_own_restaurant(client, auth):
    """The payload field does not exist, so this is a 201 with the value ignored
    rather than a 422 — but the stored status must still be pending."""
    r = await _register(client, auth, approval_status=APPROVED)
    assert r.status_code == 201, r.text
    assert r.json()["approval_status"] == PENDING


async def test_an_owner_gets_one_restaurant(client, auth):
    first = await _register(client, auth)
    assert first.status_code == 201

    second = await _register(client, auth, name="Second Kitchen")
    assert second.status_code == 409, second.text

    # A *different* owner is unaffected — the limit is per account, not global.
    other = await _register(client, auth, user_id=8, name="Someone Else's")
    assert other.status_code == 201, other.text


async def test_an_admin_cannot_register_a_restaurant(client, auth):
    """Not a permission oversight — a venue an operator created would have no
    owner to run it. Admins decide; they do not register."""
    r = await client.post("/restaurants", json=VENUE, headers=auth(1, "admin"))
    assert r.status_code == 403, r.text


async def test_a_customer_cannot_register_a_restaurant(client, auth):
    r = await client.post("/restaurants", json=VENUE, headers=auth(2, "customer"))
    assert r.status_code == 403, r.text


async def test_browse_hides_unapproved_restaurants(client, auth):
    await _register(client, auth)

    page = await client.get("/restaurants", headers=auth(2, "customer"))
    assert page.status_code == 200
    assert page.json()["items"] == []
    assert page.json()["total"] == 0


async def test_suggest_hides_unapproved_restaurants(client, auth):
    """A suggestion browse then refuses to return reads as a broken search."""
    await _register(client, auth)

    r = await client.get("/restaurants/suggest?q=Tiffin", headers=auth(2, "customer"))
    assert r.status_code == 200
    assert r.json() == []


async def test_an_owner_sees_their_own_pending_restaurant(client, auth):
    """The dashboard cannot be built from browse — this is why /mine exists."""
    await _register(client, auth)

    mine = await client.get("/restaurants/mine", headers=auth(7, "restaurant"))
    assert mine.status_code == 200, mine.text
    [venue] = mine.json()
    assert venue["name"] == "Tiffin House"
    assert venue["approval_status"] == PENDING


async def test_approval_makes_a_restaurant_discoverable(client, auth):
    created = (await _register(client, auth)).json()

    decision = await client.post(
        f"/restaurants/{created['id']}/approval",
        json={"status": APPROVED},
        headers=auth(1, "admin"),
    )
    assert decision.status_code == 200, decision.text
    assert decision.json()["approval_status"] == APPROVED

    page = await client.get("/restaurants", headers=auth(2, "customer"))
    assert [r["name"] for r in page.json()["items"]] == ["Tiffin House"]


async def test_rejection_carries_a_reason_and_closes_the_venue(client, auth):
    created = (await _register(client, auth)).json()

    r = await client.post(
        f"/restaurants/{created['id']}/approval",
        json={"status": REJECTED, "reason": "Licence not provided"},
        headers=auth(1, "admin"),
    )
    assert r.status_code == 200, r.text
    assert r.json()["approval_status"] == REJECTED
    assert r.json()["rejection_reason"] == "Licence not provided"
    # A rejected venue must not keep taking orders.
    assert r.json()["is_open"] is False


async def test_approving_after_a_rejection_clears_the_reason(client, auth):
    """A stale reason displayed beside an approved venue is worse than none."""
    created = (await _register(client, auth)).json()
    rid = created["id"]

    await client.post(
        f"/restaurants/{rid}/approval",
        json={"status": REJECTED, "reason": "Licence not provided"},
        headers=auth(1, "admin"),
    )
    r = await client.post(
        f"/restaurants/{rid}/approval", json={"status": APPROVED}, headers=auth(1, "admin")
    )
    assert r.json()["rejection_reason"] is None


async def test_only_an_admin_may_decide(client, auth):
    created = (await _register(client, auth)).json()

    for user_id, role in ((7, "restaurant"), (2, "customer")):
        r = await client.post(
            f"/restaurants/{created['id']}/approval",
            json={"status": APPROVED},
            headers=auth(user_id, role),
        )
        assert r.status_code == 403, f"{role} got {r.status_code}"


async def test_the_admin_list_shows_every_status(client, auth):
    await _register(client, auth, user_id=7)
    await _register(client, auth, user_id=8, name="Second Kitchen")

    r = await client.get("/restaurants/admin/all", headers=auth(1, "admin"))
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 2
    assert all(item["approval_status"] == PENDING for item in r.json()["items"])


async def test_the_admin_list_can_filter_to_one_status(client, auth):
    first = (await _register(client, auth, user_id=7)).json()
    await _register(client, auth, user_id=8, name="Second Kitchen")
    await client.post(
        f"/restaurants/{first['id']}/approval",
        json={"status": APPROVED},
        headers=auth(1, "admin"),
    )

    r = await client.get(
        f"/restaurants/admin/all?approval_status={PENDING}", headers=auth(1, "admin")
    )
    assert [i["name"] for i in r.json()["items"]] == ["Second Kitchen"]


async def test_the_admin_list_is_admin_only(client, auth):
    r = await client.get("/restaurants/admin/all", headers=auth(7, "restaurant"))
    assert r.status_code == 403, r.text


async def test_the_admin_route_resolves_before_restaurant_id(client, auth):
    """``/restaurants/admin/all`` must not be read as restaurant id "admin".

    FastAPI matches in declaration order and does not fall through on a failed
    path-parameter conversion, so a later declaration would 422 here instead.
    Same hazard the suggest route is guarded against.
    """
    r = await client.get("/restaurants/admin/all", headers=auth(1, "admin"))
    assert r.status_code != 422


async def test_mine_resolves_before_restaurant_id(client, auth):
    r = await client.get("/restaurants/mine", headers=auth(7, "restaurant"))
    assert r.status_code != 422
