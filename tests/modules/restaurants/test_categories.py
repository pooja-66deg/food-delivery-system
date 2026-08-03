"""Tests for renaming and deleting menu categories."""

from decimal import Decimal

import pytest

from src.core.exceptions import ConflictException, ForbiddenException, NotFoundException
from src.modules.restaurants import menu, service
from src.modules.restaurants.schemas import (
    CategoryCreate,
    CategoryUpdate,
    MenuItemCreate,
    RestaurantCreate,
)
from src.modules.users import service as users_service
from src.modules.users.schemas import UserRegister


async def _owner(db_session, email="cowner@example.com", phone="+15557780001"):
    return await users_service.register_user(
        db_session,
        UserRegister(
            email=email, phone=phone, first_name="Ola", last_name="Owner",
            password="supersecret1", role="restaurant",
        ),
    )


async def _owner_and_restaurant(db_session, **overrides):
    owner = await _owner(db_session, **overrides)
    restaurant = await service.create_restaurant(
        db_session,
        owner,
        RestaurantCreate(
            name="Pizza Palace", city="Metropolis", address_line="1 Main St",
            phone="+15550000000",
        ),
    )
    return owner, restaurant


async def _category(db_session, owner, restaurant, name="Starters", sort_order=0):
    return await menu.add_category(
        db_session, owner, restaurant.id, CategoryCreate(name=name, sort_order=sort_order)
    )


@pytest.mark.asyncio
async def test_rename_category(db_session):
    owner, restaurant = await _owner_and_restaurant(db_session)
    category = await _category(db_session, owner, restaurant)

    updated = await menu.update_category(
        db_session, owner, restaurant.id, category.id, CategoryUpdate(name="Small plates")
    )

    assert updated.name == "Small plates"
    assert updated.sort_order == 0  # untouched


@pytest.mark.asyncio
async def test_reorder_category(db_session):
    owner, restaurant = await _owner_and_restaurant(db_session)
    category = await _category(db_session, owner, restaurant)

    updated = await menu.update_category(
        db_session, owner, restaurant.id, category.id, CategoryUpdate(sort_order=3)
    )

    assert updated.sort_order == 3
    assert updated.name == "Starters"  # untouched


@pytest.mark.asyncio
async def test_delete_empty_category(db_session):
    owner, restaurant = await _owner_and_restaurant(db_session)
    category = await _category(db_session, owner, restaurant)

    await menu.delete_category(db_session, owner, restaurant.id, category.id)

    assert await menu.list_categories(db_session, restaurant.id) == []


@pytest.mark.asyncio
async def test_delete_category_with_items_is_refused(db_session):
    """An accidental click must not erase a whole menu section."""
    owner, restaurant = await _owner_and_restaurant(db_session)
    category = await _category(db_session, owner, restaurant)
    await menu.add_item(
        db_session, owner, restaurant.id,
        MenuItemCreate(category_id=category.id, name="Olives", price=Decimal("4.50")),
    )

    with pytest.raises(ConflictException):
        await menu.delete_category(db_session, owner, restaurant.id, category.id)

    assert len(await menu.list_categories(db_session, restaurant.id)) == 1


@pytest.mark.asyncio
async def test_update_category_of_another_restaurant_is_not_found(db_session):
    owner, restaurant = await _owner_and_restaurant(db_session)
    other_owner, other_restaurant = await _owner_and_restaurant(
        db_session, email="other@example.com", phone="+15557780002"
    )
    category = await _category(db_session, other_owner, other_restaurant)

    # Right owner, wrong restaurant for this category.
    with pytest.raises(NotFoundException):
        await menu.update_category(
            db_session, owner, restaurant.id, category.id, CategoryUpdate(name="Hijacked")
        )


@pytest.mark.asyncio
async def test_delete_category_requires_ownership(db_session):
    owner, restaurant = await _owner_and_restaurant(db_session)
    category = await _category(db_session, owner, restaurant)
    intruder = await _owner(db_session, email="intruder@example.com", phone="+15557780003")

    with pytest.raises((ForbiddenException, NotFoundException)):
        await menu.delete_category(db_session, intruder, restaurant.id, category.id)


@pytest.mark.asyncio
async def test_category_routes(api_client, app_session):
    from src.modules.restaurants.models import Restaurant

    await api_client.post("/auth/register", json={
        "email": "routeowner@example.com", "phone": "+15557780010", "first_name": "Route",
        "last_name": "Owner", "password": "supersecret1", "role": "restaurant"})
    tokens = (await api_client.post("/auth/login", json={
        "email": "routeowner@example.com", "password": "supersecret1"})).json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    restaurant = (await api_client.post("/restaurants", headers=headers, json={
        "name": "Route Cafe", "city": "Metropolis", "address_line": "2 Main St",
        "phone": "+15550000001"})).json()
    assert await app_session.get(Restaurant, restaurant["id"]) is not None

    category = (await api_client.post(
        f"/restaurants/{restaurant['id']}/categories", headers=headers,
        json={"name": "Drinks", "sort_order": 1})).json()

    renamed = await api_client.patch(
        f"/restaurants/{restaurant['id']}/categories/{category['id']}",
        headers=headers, json={"name": "Beverages"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Beverages"

    removed = await api_client.delete(
        f"/restaurants/{restaurant['id']}/categories/{category['id']}", headers=headers)
    assert removed.status_code == 204

    listed = await api_client.get(f"/restaurants/{restaurant['id']}/categories")
    assert listed.json() == []


@pytest.mark.asyncio
async def test_delete_category_route_reports_conflict(api_client):
    await api_client.post("/auth/register", json={
        "email": "conflict@example.com", "phone": "+15557780011", "first_name": "Con",
        "last_name": "Flict", "password": "supersecret1", "role": "restaurant"})
    tokens = (await api_client.post("/auth/login", json={
        "email": "conflict@example.com", "password": "supersecret1"})).json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    restaurant = (await api_client.post("/restaurants", headers=headers, json={
        "name": "Conflict Cafe", "city": "Metropolis", "address_line": "3 Main St",
        "phone": "+15550000002"})).json()
    category = (await api_client.post(
        f"/restaurants/{restaurant['id']}/categories", headers=headers,
        json={"name": "Mains"})).json()
    await api_client.post(f"/restaurants/{restaurant['id']}/items", headers=headers, json={
        "category_id": category["id"], "name": "Lasagne", "price": "12.00"})

    resp = await api_client.delete(
        f"/restaurants/{restaurant['id']}/categories/{category['id']}", headers=headers)

    assert resp.status_code == 409
