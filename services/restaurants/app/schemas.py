"""Request/response schemas for the restaurants domain."""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

from shared.phone import normalize_optional_phone

#: What a kitchen serves, as its owner declares it. The customer Vegetarian
#: filter reads this, so it is the owner's claim rather than something inferred
#: from which dishes happen to be flagged vegetarian today.
FoodType = Literal["veg", "non_veg", "both"]


class OpeningHourDay(BaseModel):
    """One weekday on a restaurant's weekly schedule.

    ``opens_at`` / ``closes_at`` are ``HH:MM`` in the platform's local timezone.
    A closed day keeps the times null; overnight windows use open > close
    (e.g. 22:00–02:00). Equal open and close means open all day.
    """

    day_of_week: int = Field(..., ge=0, le=6, description="Monday=0 … Sunday=6")
    opens_at: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    closes_at: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    is_closed: bool = False

    @model_validator(mode="after")
    def _window_or_closed(self) -> "OpeningHourDay":
        if self.is_closed:
            # A closed day has no window — drop any times the client sent so the
            # stored row cannot contradict the flag.
            self.opens_at = None
            self.closes_at = None
            return self
        if not self.opens_at or not self.closes_at:
            raise ValueError("opens_at and closes_at are required unless the day is closed")
        return self


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
    # Omit to accept the platform default (DELIVERY_DEFAULT_RADIUS_KM).
    delivery_radius_km: float | None = Field(default=None, gt=0, le=100)
    food_type: FoodType = "both"

    _check_phone = field_validator("phone")(normalize_optional_phone)

    # Note what is absent: approval_status. A registering owner must not be able
    # to post their own approval, so the field is not on the payload at all
    # rather than being ignored — an ignored field reads to a client as accepted.


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
    delivery_radius_km: float | None = Field(default=None, gt=0, le=100)
    # The owner's own; editing it does not re-open approval, because what a
    # kitchen serves is not what an operator vetted it for.
    food_type: FoodType | None = None
    #: Replace the whole weekly schedule when present. An empty list clears it
    #: and restores "manual ``is_open`` only" behaviour. Omitted leaves hours alone.
    opening_hours: list[OpeningHourDay] | None = None

    @field_validator("opening_hours")
    @classmethod
    def _unique_days(cls, value: list[OpeningHourDay] | None) -> list[OpeningHourDay] | None:
        if value is None:
            return value
        days = [row.day_of_week for row in value]
        if len(days) != len(set(days)):
            raise ValueError("each day_of_week may appear only once")
        return value


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
    # "pending" until an operator decides. Present on the public response
    # because the owner dashboard renders from the same shape — a customer only
    # ever sees "approved" here, since browse returns nothing else.
    approval_status: str = "pending"
    #: Populated only when rejected; what the owner has to fix.
    rejection_reason: str | None = None
    food_type: FoodType = "both"
    min_order_amount: Decimal
    # The owner's own setting, or null when they have not chosen one and the
    # platform default applies.
    delivery_radius_km: float | None = None
    image_url: str | None = None
    # Aggregated from reviews on read. None (not 0.0) when nothing is rated yet
    # — a zero would read as a terrible restaurant rather than a new one.
    rating_average: float | None = None
    review_count: int = 0
    # 1–3 ($ / $$ / $$$) from the average available-item price. None when the
    # restaurant has no orderable items to price.
    price_band: int | None = None
    # Dish names that made this restaurant match the search term. Empty unless
    # the request carried one, so the UI can say why a result is here.
    matched_items: list[str] = []
    #: Weekly schedule. Empty means none configured — ``is_open`` alone decides.
    opening_hours: list[OpeningHourDay] = []
    #: ``is_open`` and (if a schedule exists) currently inside a window. Same as
    #: ``is_open`` when no hours are set, so existing clients keep reading true.
    is_accepting_orders: bool = True
    #: Server-local clock facts. Clients format these; they do not reimplement
    #: schedule evaluation or timezone handling.
    local_day_of_week: int = Field(default=0, ge=0, le=6)
    current_closes_at: str | None = None
    open_24_hours: bool = False
    next_opens_at: str | None = None
    next_opens_day: int | None = Field(default=None, ge=0, le=6)


class AdminRestaurantRow(RestaurantResponse):
    """One line of the admin restaurant list.

    Everything the operator console shows about a venue, in the shape the
    console renders. It extends the public response rather than redefining it so
    the two cannot drift on a field they share — approval status in particular,
    which is the whole point of the screen.

    ``owner_name`` is the one addition, and it comes from a local read-model fed
    by ``user-events``: owners live in another service's database, and joining
    across that boundary is not available. Empty when no event has been seen for
    that owner yet.
    """

    owner_name: str = ""


class AdminRestaurantPage(BaseModel):
    """The admin list, paged like browse and for the same reason."""

    items: list[AdminRestaurantRow]
    total: int
    limit: int
    offset: int


class ApprovalDecision(BaseModel):
    """An operator approving or rejecting a venue.

    ``reason`` is free text and only meaningful on a rejection — it is what the
    owner is shown, so a rejection without one leaves them nothing to act on.
    Not enforced as required, because an operator rejecting obvious spam should
    not have to justify it to the system.
    """

    status: Literal["approved", "rejected"]
    reason: str | None = Field(default=None, max_length=500)


class RestaurantPage(BaseModel):
    """One page of browse results, plus the size of the whole matching set.

    An envelope rather than a bare list: paged results are meaningless without
    the total, since the client cannot otherwise tell a last page from a
    truncated one.
    """

    items: list[RestaurantResponse]
    total: int
    limit: int
    offset: int


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
    is_vegetarian: bool = False


class MenuItemUpdate(BaseModel):
    category_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = None
    price: Decimal | None = Field(default=None, gt=0)
    is_available: bool | None = None
    # An explicit null stops tracking stock for this item.
    stock_quantity: int | None = Field(default=None, ge=0)
    is_vegetarian: bool | None = None


class MenuItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category_id: int
    name: str
    description: str | None
    price: Decimal
    is_available: bool
    stock_quantity: int | None = None
    is_vegetarian: bool = False
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
    # Star -> number of reviews, all five stars always present. Distinguishes a
    # consistent 4.3 from a polarised one.
    rating_breakdown: dict[int, int] = {}
