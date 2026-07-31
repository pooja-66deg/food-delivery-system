"""Request/response schemas for the restaurants domain."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class RestaurantCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    description: str | None = None
    cuisine: str | None = Field(default=None, max_length=80)
    city: str = Field(..., min_length=1, max_length=100)
    address_line: str = Field(..., min_length=1, max_length=255)
    phone: str = Field(..., min_length=8, max_length=20)
    min_order_amount: Decimal = Field(default=Decimal("0"), ge=0)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class RestaurantUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = None
    cuisine: str | None = Field(default=None, max_length=80)
    city: str | None = Field(default=None, min_length=1, max_length=100)
    address_line: str | None = Field(default=None, min_length=1, max_length=255)
    phone: str | None = Field(default=None, min_length=8, max_length=20)
    is_open: bool | None = None
    min_order_amount: Decimal | None = Field(default=None, ge=0)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class RestaurantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    name: str
    description: str | None
    cuisine: str | None
    city: str
    address_line: str
    phone: str
    is_open: bool
    min_order_amount: Decimal
    image_url: str | None = None


class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    sort_order: int = 0


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    sort_order: int


class MenuItemCreate(BaseModel):
    category_id: int
    name: str = Field(..., min_length=1, max_length=150)
    description: str | None = None
    price: Decimal = Field(..., gt=0)
    is_available: bool = True


class MenuItemUpdate(BaseModel):
    category_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = None
    price: Decimal | None = Field(default=None, gt=0)
    is_available: bool | None = None


class MenuItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category_id: int
    name: str
    description: str | None
    price: Decimal
    is_available: bool
    image_url: str | None = None


class MenuCategoryWithItems(CategoryResponse):
    items: list[MenuItemResponse] = []


class RestaurantDetail(RestaurantResponse):
    menu: list[MenuCategoryWithItems] = []
