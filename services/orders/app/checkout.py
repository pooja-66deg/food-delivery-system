"""Validating a cart into an order.

This is the one place the split accepts a synchronous call, and it is worth
being precise about why. Checkout needs five answers only the restaurants
service can give — is the kitchen open, do these items exist at these prices, is
there stock, does it deliver here, is the minimum met — and it needs the stock
*held* against that same answer. The customer is waiting; there is no version of
this that is honestly asynchronous.

What is asynchronous is everything after: the order commits, and payments,
delivery, restaurants and notifications all learn about it from an event.

The address comes from the local read-model rather than the users service, so
checkout has exactly one sync dependency rather than two. The rest of the guard
rails live in ``shared/http_client.py``: a short timeout, a circuit breaker, and
a 503 that says "try again" rather than a 4xx that says "you were wrong".
"""

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.cart_schemas import CheckoutRequest, ValidatedOrder, ValidatedOrderItem
from app.clients import restaurants
from app.models import AddressSnapshot
from shared.errors import AppException, NotFoundException


class CheckoutError(AppException):
    """A cart that cannot become an order, with a code the frontend handles.

    The codes are unchanged from the monolith — EMPTY_CART, RESTAURANT_CLOSED,
    ITEM_OUT_OF_STOCK, PRICE_MISMATCH_REFRESH, ADDRESS_OUT_OF_ZONE,
    MIN_ORDER_NOT_MET — because the frontend keys its messaging off them and the
    split must be invisible to it.
    """

    def __init__(self, code: str, message: str):
        super().__init__(message, status_code=409, details={"code": code})
        self.code = code


async def validate_checkout(
    session: AsyncSession,
    cart,
    customer_id: int,
    request: CheckoutRequest,
    auth_header: str,
) -> ValidatedOrder:
    """Turn a cart into a validated order, reserving stock as it goes."""
    if not cart.items or cart.restaurant_id is None:
        raise CheckoutError("EMPTY_CART", "Your cart is empty.")

    # Checked here, against what the customer was shown, before anything is
    # asked of another service: a stale cart should not cost a network call.
    if request.price_hash != cart.price_hash:
        raise CheckoutError("PRICE_MISMATCH_REFRESH", "Prices changed. Please review your cart.")

    address = await session.get(AddressSnapshot, request.address_id)
    if address is None or address.user_id != customer_id:
        # Also the answer when the address exists but its event has not arrived
        # yet. Rare, self-correcting on retry, and far better than accepting an
        # order for somewhere we cannot confirm we deliver.
        raise NotFoundException("Address", str(request.address_id))

    response = await restaurants().post(
        f"/restaurants/{cart.restaurant_id}/validate-order",
        json={
            "items": [
                {
                    "menu_item_id": i.menu_item_id,
                    "quantity": i.quantity,
                    "unit_price": str(i.unit_price),
                }
                for i in cart.items
            ],
            "address": {
                "city": address.city,
                "latitude": address.latitude,
                "longitude": address.longitude,
            },
            "reserve": True,
        },
        auth_header=auth_header,
    )

    if response.status_code == 404:
        raise NotFoundException("Restaurant", str(cart.restaurant_id))
    if response.status_code >= 400:
        # Not a 5xx — the client raises 503 for those — so this is the
        # restaurants service refusing for a reason it did not encode.
        raise CheckoutError("CHECKOUT_FAILED", "Your cart could not be checked out.")

    verdict = response.json()
    if not verdict.get("ok"):
        raise CheckoutError(
            verdict.get("code") or "CHECKOUT_FAILED",
            verdict.get("message") or "Your cart could not be checked out.",
        )

    return ValidatedOrder(
        restaurant_id=verdict["restaurant_id"],
        address_id=address.address_id,
        subtotal=Decimal(str(verdict["subtotal"])),
        items=[
            ValidatedOrderItem(
                menu_item_id=line["menu_item_id"],
                name=line["name"],
                unit_price=Decimal(str(line["unit_price"])),
                quantity=line["quantity"],
                line_total=Decimal(str(line["line_total"])),
            )
            for line in verdict["items"]
        ],
    )


async def release_stock(restaurant_id: int, lines, auth_header: str) -> None:
    """Put a cancelled order's stock back.

    Best-effort on purpose. The order is already cancelled and committed; if the
    restaurants service cannot be reached, failing the cancellation would leave
    the customer stuck with an order they asked to cancel. The cost of the other
    choice is a few portions showing as unavailable until an owner corrects
    them — recoverable, where a stuck order is not.
    """
    import logging

    try:
        await restaurants().post(
            f"/restaurants/{restaurant_id}/release-stock",
            json={
                "items": [
                    {
                        "menu_item_id": line.menu_item_id,
                        "quantity": line.quantity,
                        "unit_price": str(line.unit_price),
                    }
                    for line in lines
                ]
            },
            auth_header=auth_header,
        )
    except Exception:  # noqa: BLE001 — see docstring
        logging.getLogger(__name__).exception(
            "Could not release stock for restaurant %s; it will need correcting by hand",
            restaurant_id,
        )
