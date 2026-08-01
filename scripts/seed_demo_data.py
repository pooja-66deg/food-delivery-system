"""Seed a handful of demo restaurants so discovery features have data.

A fresh database has no restaurants, which makes browse, search, typeahead and
the popular-cuisine chips all look broken when they are merely empty.

Run with:

    python -m scripts.seed_demo_data

Safe to run repeatedly — existing rows are left alone.
"""

import asyncio
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database import async_session
from src.modules.restaurants.models import Restaurant
from src.modules.users.models import User
from src.modules.users.service import hash_password

DEMO_OWNER_EMAIL = "demo.owner@example.com"
DEMO_OWNER_PHONE = "+15550100100"
DEMO_OWNER_PASSWORD = "supersecret1"

# Spread across cities and cuisines so city filtering, cuisine search, and the
# popular-cuisine ordering all have something meaningful to show.
DEMO_RESTAURANTS = [
    ("Pizza Palace", "Italian", "Metropolis", "Wood-fired sourdough pizzas."),
    ("Pasta Place", "Italian", "Metropolis", "Hand-rolled pasta, daily specials."),
    ("Trattoria Nove", "Italian", "Gotham", "Family recipes from Napoli."),
    ("Sushi Spot", "Japanese", "Gotham", "Omakase counter and rolls."),
    ("Ramen Room", "Japanese", "Star City", "Tonkotsu simmered 18 hours."),
    ("Curry Corner", "Indian", "Metropolis", "Slow-cooked regional curries."),
    ("Bangkok Bowl", "Thai", "Star City", "Street-food classics, fiery som tam."),
    ("Taco Tuesday", "Mexican", "Gotham", "Corn tortillas pressed to order."),
]


async def _demo_owner(session: AsyncSession) -> User:
    """Return the demo owner, creating it only if absent."""
    owner = await session.scalar(select(User).where(User.email == DEMO_OWNER_EMAIL))
    if owner is not None:
        return owner

    owner = User(
        email=DEMO_OWNER_EMAIL,
        phone=DEMO_OWNER_PHONE,
        first_name="Demo",
        last_name="Owner",
        hashed_password=hash_password(DEMO_OWNER_PASSWORD),
        role="restaurant",
    )
    session.add(owner)
    await session.flush()
    return owner


async def seed(session: AsyncSession) -> int:
    """Create any missing demo restaurants. Returns how many were added."""
    owner = await _demo_owner(session)

    existing = set(await session.scalars(select(Restaurant.name)))
    added = 0
    for index, (name, cuisine, city, description) in enumerate(DEMO_RESTAURANTS):
        if name in existing:
            continue
        session.add(
            Restaurant(
                owner_id=owner.id,
                name=name,
                cuisine=cuisine,
                city=city,
                description=description,
                address_line=f"{index + 1} Market Street",
                phone="+15550000000",
                is_open=True,
                min_order_amount=Decimal("10.00"),
            )
        )
        added += 1

    await session.commit()
    return added


async def main() -> None:
    async with async_session() as session:
        added = await seed(session)
    print(f"Seeded {added} restaurant(s); {len(DEMO_RESTAURANTS)} in the demo set.")
    print(f"Owner login: {DEMO_OWNER_EMAIL} / {DEMO_OWNER_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(main())
