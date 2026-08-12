"""Who may see a venue that has not been approved.

Browse, search, suggest, cities and popular cuisines all filtered on approval
status — ``discovery.py`` calls that filter "the boundary between 'a row exists'
and 'a customer may see it'". Two routes did not: the detail page and the
internal ``/lookup``. Ids are sequential, so walking them returned every pending
applicant's venue name, street address and business phone to an anonymous caller,
before an operator had reviewed the application.

The gate cannot simply be "authenticated", because two callers legitimately need
to see an unapproved venue: its own owner, and an admin deciding on it.
"""

import pytest

from app.models import APPROVED, PENDING, Restaurant


@pytest.fixture
async def pending_venue(session):
    venue = Restaurant(
        owner_id=4242, name="Not Yet Open", city="Surat",
        address_line="9 Applicant Lane", phone="+919999900001",
        approval_status=PENDING, is_open=False,
    )
    session.add(venue)
    await session.commit()
    await session.refresh(venue)
    return venue


@pytest.fixture
async def approved_venue(session):
    venue = Restaurant(
        owner_id=4243, name="Open For Business", city="Surat",
        address_line="1 Trading Street", phone="+919999900002",
        approval_status=APPROVED, is_open=True,
    )
    session.add(venue)
    await session.commit()
    await session.refresh(venue)
    return venue


class TestDetailPage:
    async def test_anonymous_cannot_read_a_pending_venue(self, client, pending_venue):
        """404, not 403 — "there is a venue here you may not see" is itself the
        fact being withheld, and ids are guessable."""
        r = await client.get(f"/restaurants/{pending_venue.id}")
        assert r.status_code == 404, r.text
        assert "9 Applicant Lane" not in r.text
        assert "+919999900001" not in r.text

    async def test_anonymous_can_still_read_an_approved_venue(
        self, client, approved_venue
    ):
        """The gate must not cost anonymous browsing, which is the normal case."""
        r = await client.get(f"/restaurants/{approved_venue.id}")
        assert r.status_code == 200, r.text
        assert r.json()["name"] == "Open For Business"

    async def test_a_customer_cannot_read_a_pending_venue(
        self, client, pending_venue, auth
    ):
        r = await client.get(
            f"/restaurants/{pending_venue.id}",
            headers=auth(user_id=777, role="customer"),
        )
        assert r.status_code == 404, r.text

    async def test_the_owner_can_read_their_own_pending_venue(
        self, client, pending_venue, auth
    ):
        """An applicant has to be able to see what they submitted — the dashboard
        is otherwise empty while they wait."""
        r = await client.get(
            f"/restaurants/{pending_venue.id}",
            headers=auth(user_id=pending_venue.owner_id, role="restaurant"),
        )
        assert r.status_code == 200, r.text
        assert r.json()["approval_status"] == PENDING

    async def test_another_owner_cannot_read_it(
        self, client, pending_venue, auth
    ):
        r = await client.get(
            f"/restaurants/{pending_venue.id}",
            headers=auth(user_id=pending_venue.owner_id + 1, role="restaurant"),
        )
        assert r.status_code == 404, r.text

    async def test_an_admin_can_read_it(self, client, pending_venue, auth):
        r = await client.get(
            f"/restaurants/{pending_venue.id}",
            headers=auth(user_id=1, role="admin"),
        )
        assert r.status_code == 200, r.text


class TestInternalLookup:
    async def test_lookup_requires_a_token(self, client, approved_venue):
        """It is a service-to-service route and the module docstring says these
        are "guarded by the caller's own token". These two were not."""
        r = await client.get(f"/restaurants/lookup?ids={approved_venue.id}")
        assert r.status_code == 401, r.text

    async def test_lookup_omits_pending_venues(
        self, client, pending_venue, approved_venue, auth
    ):
        """A favourites list only ever holds venues the customer could already
        see, so filtering costs the caller nothing."""
        r = await client.get(
            f"/restaurants/lookup?ids={pending_venue.id},{approved_venue.id}",
            headers=auth(user_id=777, role="customer"),
        )
        assert r.status_code == 200, r.text
        assert [v["id"] for v in r.json()] == [approved_venue.id]

    async def test_item_lookup_requires_a_token(self, client):
        r = await client.get("/restaurants/items/lookup?ids=1")
        assert r.status_code == 401, r.text

    async def test_an_out_of_range_id_does_not_fail_the_batch(
        self, client, approved_venue, auth
    ):
        """2147483648 reached asyncpg and raised while binding an int4, turning
        the whole lookup into a 500. One unusable id should cost that id only."""
        r = await client.get(
            f"/restaurants/lookup?ids={approved_venue.id},2147483648",
            headers=auth(user_id=777, role="customer"),
        )
        assert r.status_code == 200, r.text
        assert [v["id"] for v in r.json()] == [approved_venue.id]


class TestBoundedIds:
    async def test_detail_rejects_an_out_of_int32_id(self, client):
        """422 rather than the 500 an int4 bind produced. 2147483647 already
        answered a clean 404, so the boundary was the whole bug."""
        assert (await client.get("/restaurants/2147483648")).status_code == 422
        assert (await client.get("/restaurants/2147483647")).status_code == 404

    async def test_reviews_listing_rejects_it_too(self, client):
        """Unauthenticated, which is what made this one reachable by anyone."""
        assert (await client.get("/reviews/restaurant/2147483648")).status_code == 422

    async def test_browse_offset_beyond_bigint_is_rejected(self, client):
        assert (await client.get("/restaurants?offset=99999999999999999999")).status_code == 422
