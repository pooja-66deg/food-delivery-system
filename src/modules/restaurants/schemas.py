"""Request/response schemas for the restaurants domain."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from src.core.phone import normalize_optional_phone


class RestaurantCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    description: str | None = None
    cuisine: str | None = Field(default=None, max_length=80)
    city: str = Field(..., min_length=1, max_length=100)
    address_line: str = Field(..., min_length=1, max_length=255)
    phone: str
    min_order_amount: Decimal = Field(default=Decimal("0"), ge=0)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

    _check_phone = field_validator("phone")(normalize_optional_phone)


class RestaurantUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = None
    cuisine: str | None = Field(default=None, max_length=80)
    city: str | None = Field(default=None, min_length=1, max_length=100)
    address_line: str | None = Field(default=None, min_length=1, max_length=255)
    phone: str | None = None
    is_open: bool | None = None

    _check_phone = field_validator("phone")(normalize_optional_phone)
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


class RestaurantSuggestion(BaseModel):
    """Trimmed payload for typeahead — enough to label a suggestion, no more."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    city: str
    cuisine: str | None


class CuisineCount(BaseModel):
    cuisine: str
    count: int


class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    sort_order: int = 0


class CategoryUpdate(BaseModel):
    """Editable category fields; omitted fields are left alone."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    sort_order: int | None = None


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
    # Omit (or send null) to leave stock untracked.
    stock_quantity: int | None = Field(default=None, ge=0)


class MenuItemUpdate(BaseModel):
    category_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = None
    price: Decimal | None = Field(default=None, gt=0)
    is_available: bool | None = None
    # An explicit null stops tracking stock for this item.
    stock_quantity: int | None = Field(default=None, ge=0)


class MenuItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category_id: int
    name: str
    description: str | None
    price: Decimal
    is_available: bool
    stock_quantity: int | None = None
    image_url: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def in_stock(self) -> bool:
        """Whether a customer can order this right now.

        One field for clients to read: the owner's switch and the stock count
        both have to allow it. Untracked stock never blocks.
        """
        return self.is_available and (self.stock_quantity is None or self.stock_quantity > 0)


class MenuCategoryWithItems(CategoryResponse):
    items: list[MenuItemResponse] = []


class RestaurantDetail(RestaurantResponse):
    menu: list[MenuCategoryWithItems] = []
