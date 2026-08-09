"""Business logic for the users domain."""

from typing import Any, Mapping

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from shared.errors import ConflictException, UnauthorizedException
from app.jwt_tokens import create_access_token, create_refresh_token, verify_token
from app.security import hash_password, verify_password
from app import outbox
from app import tokens as token_store
from app.models import User
from app.schemas import RestaurantSignup, TokenResponse, UserRegister

__all__ = [
    "register_user", "login", "refresh_tokens", "logout",
    "verify_password", "change_password",
    "request_password_reset", "reset_password",
    "is_revoked", "generation_matches",
    "apply_restaurant_decision", "publish_restaurant_registration",
    "PENDING_APPROVAL_MESSAGE", "REJECTED_MESSAGE",
]

_BLOCKLIST_KEY = "jwt:blocklist:{jti}"
RESET_PREFIX = "pwd_reset"


async def request_password_reset(session: AsyncSession, redis, email: str) -> str | None:
    """Issue a single-use reset token for ``email`` if an active account exists.

    Returns the plaintext token for the caller to deliver, or None when there is
    no matching account. The token's SHA-256 hash is what Redis holds; the
    plaintext is never persisted, so it exists only in the email.

    Returning None rather than raising is what lets the route answer identically
    either way — see the router for why that matters.
    """
    user = await session.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active:
        return None
    return await token_store.issue_single_use(
        redis, RESET_PREFIX, user.id, settings.password_reset_ttl_seconds
    )


async def reset_password(session: AsyncSession, redis, token: str, new_password: str) -> None:
    """Consume a reset token and set a new password.

    Raises UnauthorizedException if the token is unknown, expired, or already
    spent — one message for all three, so the endpoint cannot be used to learn
    which tokens exist.

    Every existing session is evicted by the generation bump. That is the point
    of a reset rather than a convenience: whoever locked the account's owner out
    loses their access at the moment the owner takes it back.
    """
    user_id = await token_store.consume_single_use(redis, RESET_PREFIX, token)
    if user_id is None:
        raise UnauthorizedException("Invalid or expired reset token")
    user = await session.get(User, user_id)
    if user is None:
        raise UnauthorizedException("Invalid or expired reset token")
    user.hashed_password = hash_password(new_password)
    user.session_generation += 1
    await session.commit()


async def change_password(
    session: AsyncSession, user: User, current_password: str, new_password: str
) -> TokenResponse:
    """Change the password of a signed-in user and evict every other session.

    Returns a fresh token pair carrying the new generation, so the caller stays
    signed in on the device that made the change.
    """
    if not verify_password(current_password, user.hashed_password):
        raise UnauthorizedException("Current password is incorrect")
    user.hashed_password = hash_password(new_password)
    user.session_generation += 1
    await session.commit()
    await session.refresh(user)
    return _issue_tokens(user)


async def _blocklist(redis, jti: str, ttl_seconds: int) -> None:
    await redis.set(_BLOCKLIST_KEY.format(jti=jti), "1", ex=ttl_seconds)


async def is_revoked(redis, jti: str | None) -> bool:
    """True if this token's jti has been blocklisted by a logout."""
    if not jti:
        return False
    return await redis.get(_BLOCKLIST_KEY.format(jti=jti)) is not None


def generation_matches(payload: Mapping[str, Any], user: User) -> bool:
    """True if the token was minted for the user's current session generation.

    A missing ``gen`` claim reads as 0 — the default — so tokens issued before
    this claim existed keep working until the first eviction.
    """
    return int(payload.get("gen") or 0) == user.session_generation


def _issue_tokens(user: User) -> TokenResponse:
    """Build an access/refresh token pair for a user."""
    claims = {"sub": str(user.id), "role": user.role, "gen": user.session_generation}
    return TokenResponse(
        access_token=create_access_token(claims),
        refresh_token=create_refresh_token(claims),
        expires_in=settings.jwt_expiration_minutes * 60,
    )


async def register_user(session: AsyncSession, data: UserRegister) -> User:
    """Create a new user with a hashed password.

    A restaurant applicant is created *inactive*: their venue has to be approved
    by an operator before it may trade, and an account that could sign in while
    that decision was outstanding would let them build a listing the operator has
    not yet agreed to host. login() rejects inactive accounts already, so the
    gate is this one flag rather than a second code path — see
    ``PENDING_APPROVAL_MESSAGE`` for what they are told.

    Raises ConflictException if the email or phone is already registered.
    """
    existing = await session.scalar(
        select(User).where(or_(User.email == data.email, User.phone == data.phone))
    )
    if existing is not None:
        if existing.email == data.email:
            raise ConflictException("Email already registered")
        raise ConflictException("Phone already registered")

    awaiting_approval = data.role == "restaurant"
    user = User(
        email=data.email,
        phone=data.phone,
        first_name=data.first_name,
        last_name=data.last_name,
        hashed_password=hash_password(data.password),
        role=data.role,
        is_active=not awaiting_approval,
        approval_status="pending" if awaiting_approval else None,
    )
    session.add(user)
    try:
        # Flush rather than commit first: it assigns user.id, which the event
        # needs, and still raises the duplicate below. The event then commits in
        # the same transaction as the user — the whole point of the outbox.
        await session.flush()
        publish_user(session, user)
        if awaiting_approval:
            # Same transaction as the user, so there is no state where an
            # account exists with no venue for an operator to review — the
            # applicant would be locked out with nothing pending to unlock them.
            publish_restaurant_registration(session, user, data.restaurant)
        await session.commit()
    except IntegrityError:
        # Lost the race against a concurrent registration with the same
        # email/phone — surface a clean 409 instead of a 500.
        await session.rollback()
        raise ConflictException("Email or phone already registered")
    await session.refresh(user)
    return user


def publish_restaurant_registration(
    session: AsyncSession, user: User, details: RestaurantSignup
) -> None:
    """Hand a new applicant's venue to the service that owns restaurants.

    A separate topic from ``user-events`` on purpose. That one is subscribed to
    by everybody, and these are business contact details — a street address and a
    phone number — which only the restaurants service has any reason to hold.
    Putting them on the general topic would hand them to the delivery service's
    driver roster and every other consumer of a display name.

    Asynchronous, and safe to be: the one thing restaurant creation rejects is a
    second venue for the same owner, and this owner was created moments ago in
    the same transaction, so there is nothing for it to collide with. Everything
    else was validated by RestaurantSignup before we got here.
    """
    outbox.record_event(
        session, "restaurant-registrations", str(user.id),
        {
            "owner_id": user.id,
            "name": details.name,
            "city": details.city,
            "address_line": details.address_line,
            "phone": details.phone,
            "cuisine": details.cuisine,
            "description": details.description,
            "food_type": details.food_type,
        },
    )


async def apply_restaurant_decision(
    session: AsyncSession, owner_id: int, status: str
) -> bool:
    """Mirror an operator's approval decision onto the owner's account.

    This is the step that actually lets an approved owner in: registration left
    them inactive, and nothing else ever sets that flag back. Driven by an event
    rather than a call from the restaurants service so that approving a venue
    does not fail when this service is restarting — the decision is already
    committed there, and the account catches up when the event is delivered.

    Returns whether anything changed, which is what tells the caller to announce
    the user afresh. At-least-once delivery means this runs again on redelivery,
    and the second run is a no-op rather than a second announcement.

    Only ever *grants* access on "approved". A rejection records the status so
    login can explain itself, but deliberately does not deactivate an account
    that is already live: by the time a venue is rejected the owner may have been
    trading for a year, and a rejection is a decision about a listing, not a ban
    on the person.
    """
    user = await session.get(User, owner_id)
    if user is None or user.role != "restaurant":
        return False

    was_active, previous = user.is_active, user.approval_status
    user.approval_status = status
    if status == "approved":
        user.is_active = True

    if user.is_active == was_active and user.approval_status == previous:
        return False

    publish_user(session, user)
    await session.commit()
    return True


def publish_user(session: AsyncSession, user: User) -> None:
    """Announce a user's current state to whoever keeps a copy of it.

    Services do not read the users table — it is in another database — so those
    that need a name or a role keep a local read-model and update it from this.
    The delivery service's driver roster is the first such consumer.

    Two topics, deliberately. ``user-events`` carries what several services
    need — a role, a display name, whether the account is active — and anyone
    may subscribe. Contact details go to ``user-contact-events``, which is
    restricted to services with a reason to hold them: notifications, which
    sends to an address, and admin, which displays one to a human operator.

    Splitting them is the whole point: on one topic, every consumer of a name
    would also receive an email address it has no use for and would then be
    storing. Never the password hash, on either.
    """
    outbox.record_event(
        session, "user-events", str(user.id),
        {
            "user_id": user.id,
            "role": user.role,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "is_active": user.is_active,
        },
    )
    outbox.record_event(
        session, "user-contact-events", str(user.id),
        {"user_id": user.id, "email": user.email, "phone": user.phone},
    )


async def refresh_tokens(session: AsyncSession, redis, refresh_token: str) -> TokenResponse:
    """Validate a refresh token and issue a new pair, rotating (revoking) the old one."""
    payload = verify_token(refresh_token)
    if payload.get("type") != "refresh":
        raise UnauthorizedException("Invalid token type")

    jti = payload.get("jti")
    if await is_revoked(redis, jti):
        raise UnauthorizedException("Token revoked")

    try:
        user_id = int(payload.get("sub"))
    except (TypeError, ValueError):
        raise UnauthorizedException("Invalid token")

    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise UnauthorizedException("User not found or inactive")
    if not generation_matches(payload, user):
        raise UnauthorizedException("Session expired")

    if jti:
        # rotation: the presented refresh token can't be reused
        await _blocklist(redis, jti, settings.jwt_refresh_expiration_days * 86400)
    return _issue_tokens(user)


async def logout(redis, refresh_token: str, access_token: str | None = None) -> None:
    """Revoke the presented tokens by blocklisting their jtis.

    Both are revoked: dropping only the refresh token would leave the access
    token usable for the rest of its lifetime. Tokens that are already invalid
    or expired are ignored.
    """
    await _revoke(redis, refresh_token, settings.jwt_refresh_expiration_days * 86400)
    if access_token:
        await _revoke(redis, access_token, settings.jwt_expiration_minutes * 60)


async def _revoke(redis, token: str, ttl_seconds: int) -> None:
    try:
        payload = verify_token(token)
    except UnauthorizedException:
        return
    jti = payload.get("jti")
    if jti:
        await _blocklist(redis, jti, ttl_seconds)


async def login(session: AsyncSession, email: str, password: str) -> TokenResponse:
    """Authenticate by email/password and issue tokens.

    Raises UnauthorizedException on unknown email, wrong password, or inactive
    account. The same error is used for all cases to avoid leaking which emails
    are registered.

    A restaurant applicant is the one exception, and only *after* their password
    has been checked. Telling them "still waiting on approval" is something they
    need to hear — otherwise a correct password looks indistinguishable from a
    typo and they re-register — and by that point it discloses nothing: anyone
    holding the right password for an address already knows it is registered.
    Getting the password wrong still yields the generic error, so the enumeration
    property that matters is unchanged.
    """
    user = await session.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(password, user.hashed_password):
        raise UnauthorizedException("Invalid email or password")
    if not user.is_active:
        raise UnauthorizedException(_inactive_reason(user))
    return _issue_tokens(user)


#: Said to an applicant whose venue an operator has not decided on yet.
PENDING_APPROVAL_MESSAGE = (
    "Your restaurant registration is awaiting approval. "
    "We'll email you as soon as it has been reviewed."
)

#: Said to one whose venue was turned down. The reason lives on the restaurant
#: in the restaurants service and is shown in the owner console — which a
#: rejected applicant cannot reach — so this points at a human instead of
#: repeating a reason this service does not have.
REJECTED_MESSAGE = (
    "Your restaurant registration was not approved. "
    "Please contact support if you think this is a mistake."
)


def _inactive_reason(user: User) -> str:
    """Why this account cannot sign in, in words meant for its owner.

    Only the two application outcomes get their own wording. An account that is
    inactive for any other reason — an operator switched it off, or it predates
    approval_status entirely — falls back to the generic message, because
    guessing out loud is worse than saying little.
    """
    if user.approval_status == "pending":
        return PENDING_APPROVAL_MESSAGE
    if user.approval_status == "rejected":
        return REJECTED_MESSAGE
    return "Invalid email or password"
