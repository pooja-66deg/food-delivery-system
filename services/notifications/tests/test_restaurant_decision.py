"""Telling a restaurant owner what an operator decided.

This service sends it because no other one can. The restaurants service makes
the decision but holds no addresses — it deliberately does not subscribe to
``user-contact-events`` — and the owner cannot be told in the app, because being
locked out of the app is the state the decision resolves.

So the tests are mostly about the seam: a status arrives, an address is looked
up here, and a mail goes out. What happens when the address has not arrived yet
matters as much as the happy path.
"""

from sqlalchemy import select

from app.consumer import _handle_restaurant
from app.models import Contact, Notification

APPROVED = {"owner_id": 7, "name": "Tiffin House", "approval_status": "approved"}


async def _sent(session) -> list[Notification]:
    return list(await session.scalars(select(Notification).order_by(Notification.id)))


async def _with_contact(session, user_id=7, email="owner@example.com"):
    session.add(Contact(user_id=user_id, email=email))
    await session.commit()


async def test_approval_emails_the_owner(session, monkeypatch):
    sent: list[tuple] = []

    async def _dispatch(channel, to, message, subject=None):
        sent.append((channel, to, subject, message))
        return True

    from app import senders
    monkeypatch.setattr(senders, "dispatch", _dispatch)
    await _with_contact(session)

    await _handle_restaurant(session, APPROVED)

    assert len(sent) == 1
    channel, to, subject, message = sent[0]
    assert channel == "EMAIL"
    assert to == "owner@example.com"
    assert "approved" in subject.lower()
    assert "Tiffin House" in message


async def test_rejection_is_worded_differently(session, monkeypatch):
    sent: list[tuple] = []

    async def _dispatch(channel, to, message, subject=None):
        sent.append((channel, to, subject, message))
        return True

    from app import senders
    monkeypatch.setattr(senders, "dispatch", _dispatch)
    await _with_contact(session)

    await _handle_restaurant(
        session, {**APPROVED, "approval_status": "rejected"}
    )

    [(_, _, subject, message)] = sent
    assert "approved" not in subject.lower()
    assert "not approved" in message


async def test_a_pending_restaurant_is_not_mailed_about(session, monkeypatch):
    """``restaurant-events`` fires on every change to a restaurant, not only on
    a decision — a rename or a kitchen closing produces one too. Mailing "we
    received it" on each would be noise about nothing."""
    sent: list[tuple] = []

    async def _dispatch(*args, **kwargs):
        sent.append(args)
        return True

    from app import senders
    monkeypatch.setattr(senders, "dispatch", _dispatch)
    await _with_contact(session)

    await _handle_restaurant(session, {**APPROVED, "approval_status": "pending"})

    assert sent == []
    assert await _sent(session) == []


async def test_an_unknown_owner_is_not_a_failure(session, monkeypatch):
    """The address travels on its own topic and may not have landed yet.

    Raising would redeliver forever. Nothing is retried because an approval whose
    mail was missed is visible the moment the owner tries to sign in — which, by
    then, works.
    """
    async def _dispatch(*args, **kwargs):  # pragma: no cover — must not be called
        raise AssertionError("should not send without an address")

    from app import senders
    monkeypatch.setattr(senders, "dispatch", _dispatch)

    await _handle_restaurant(session, APPROVED)  # no Contact row exists
    assert await _sent(session) == []


async def test_a_failed_send_is_still_recorded(session, monkeypatch):
    """A sender that returns False leaves a row marked undelivered rather than
    no row at all — otherwise nobody can tell a mail that failed from one that
    was never attempted."""
    async def _dispatch(*args, **kwargs):
        return False

    from app import senders
    monkeypatch.setattr(senders, "dispatch", _dispatch)
    await _with_contact(session)

    await _handle_restaurant(session, APPROVED)

    [row] = await _sent(session)
    assert row.delivered is False
    assert row.type == "restaurant.approved"


async def test_a_raising_sender_does_not_fail_the_event(session, monkeypatch):
    """The decision it describes already happened. Letting the exception out
    would redeliver an event whose only remaining effect is a duplicate mail."""
    async def _dispatch(*args, **kwargs):
        raise RuntimeError("smtp exploded")

    from app import senders
    monkeypatch.setattr(senders, "dispatch", _dispatch)
    await _with_contact(session)

    await _handle_restaurant(session, APPROVED)

    [row] = await _sent(session)
    assert row.delivered is False


async def test_an_incomplete_payload_is_ignored(session):
    await _handle_restaurant(session, {"owner_id": 7})
    await _handle_restaurant(session, {"approval_status": "approved"})
    assert await _sent(session) == []
