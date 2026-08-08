"""Schemas for the cart & checkout domain."""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class CartItemView(BaseModel):
    menu_item_id: int
    name: str
    unit_price: Decimal
    quantity: int
    line_total: Decimal


class CartView(BaseModel):
    restaurant_id: int | None = None
    items: list[CartItemView] = []
    subtotal: Decimal = Decimal("0")
    price_hash: str = ""


class AddToCart(BaseModel):
    menu_item_id: int
    quantity: int = Field(default=1, ge=1)


class UpdateCartItem(BaseModel):
    quantity: int = Field(..., ge=0)  # 0 removes the line


class ReorderRequest(BaseModel):
    order_id: int


class ReorderResponse(BaseModel):
    """The refilled cart, plus the lines that could not be carried over.

    ``skipped`` is part of the success response rather than an error: one
    delisted side dish must not fail the whole reorder, but the customer has to
    be told what is missing before they pay.
    """

    cart: CartView
    skipped: list[str] = []


class CheckoutRequest(BaseModel):
    address_id: int
    price_hash: str
    payment_method: Literal["COD", "CARD"] = "COD"


class ValidatedOrderItem(BaseModel):
    menu_item_id: int
    name: str
    unit_price: Decimal
    quantity: int
    line_total: Decimal


class ValidatedOrder(BaseModel):
    restaurant_id: int
    address_id: int
    items: list[ValidatedOrderItem]
    subtotal: Decimal
