"""The Vegetarian filter reads the owner's declaration, not the menu.

This changed meaning deliberately. It used to mean "has at least one available
vegetarian dish", which matched almost every restaurant and so filtered nothing
useful — a steakhouse with a side salad passed. It now means "the owner declared
this a vegetarian kitchen", which is the question a customer is actually asking.

``menu_items.is_vegetarian`` still exists and still marks individual dishes; it
is simply no longer what this filter reads.
"""

from app.models import APPROVED

VENUE = {"city": "Surat", "address_line": "1 KK Road", "phone": "+919876500001"}


async def _approved(client, auth, user_id, name, food_type):
    created = (
        await client.post(
            "/restaurants",
            json={**VENUE, "name": name, "food_type": food_type},
            headers=auth(user_id, "restaurant"),
        )
    ).json()
    await client.post(
        f"/restaurants/{created['id']}/approval",
        json={"status": APPROVED},
        headers=auth(1, "admin"),
    )
    return created


async def _browse(client, auth, query=""):
    page = await client.get(f"/restaurants{query}", headers=auth(2, "customer"))
    assert page.status_code == 200, page.text
    return sorted(item["name"] for item in page.json()["items"])


async def test_food_type_defaults_to_both(client, auth):
    """The honest answer for a kitchen nobody has asked yet. Defaulting to
    "veg" would assert a claim the owner never made."""
    r = await client.post(
        "/restaurants", json={**VENUE, "name": "Unstated"}, headers=auth(7, "restaurant")
    )
    assert r.json()["food_type"] == "both"


async def test_vegetarian_filter_returns_only_veg_kitchens(client, auth):
    await _approved(client, auth, 7, "Pure Veg", "veg")
    await _approved(client, auth, 8, "Grill House", "non_veg")
    await _approved(client, auth, 9, "Mixed Kitchen", "both")

    assert await _browse(client, auth) == ["Grill House", "Mixed Kitchen", "Pure Veg"]
    assert await _browse(client, auth, "?vegetarian_only=true") == ["Pure Veg"]


async def test_a_both_kitchen_is_not_vegetarian(client, auth):
    """Stated as its own test because it is the judgement call in this feature.

    A customer filtering for vegetarian wants a vegetarian restaurant, not one
    that also serves meat — so "both" is excluded. If that is ever wrong, this
    is the test that should fail and be argued with.
    """
    await _approved(client, auth, 9, "Mixed Kitchen", "both")

    assert await _browse(client, auth, "?vegetarian_only=true") == []


async def test_an_owner_can_change_their_food_type(client, auth):
    created = await _approved(client, auth, 7, "Switching", "non_veg")
    assert await _browse(client, auth, "?vegetarian_only=true") == []

    r = await client.patch(
        f"/restaurants/{created['id']}",
        json={"food_type": "veg"},
        headers=auth(7, "restaurant"),
    )
    assert r.status_code == 200, r.text
    assert r.json()["food_type"] == "veg"
    # Still approved: what a kitchen serves is not what an operator vetted it for.
    assert r.json()["approval_status"] == APPROVED
    assert await _browse(client, auth, "?vegetarian_only=true") == ["Switching"]


async def test_an_unknown_food_type_is_rejected(client, auth):
    r = await client.post(
        "/restaurants",
        json={**VENUE, "name": "Nonsense", "food_type": "vegan"},
        headers=auth(7, "restaurant"),
    )
    assert r.status_code == 422, r.text
