"""Request/response schemas for the users domain."""

import re
from datetime import datetime
from typing import Literal

from pydantic import (
    BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator,
)

from shared.phone import normalize_optional_phone

# Roles a user may self-register as. "admin" is provisioned separately, never
# via public registration.
SelfServiceRole = Literal["customer", "restaurant", "driver"]

_NAME_RE = re.compile(r"[A-Za-z ]+")   # letters and spaces only — no digits/specials


def _validate_name(v: str | None) -> str | None:
    if v is None:
        return v
    s = v.strip()
    if not _NAME_RE.fullmatch(s):
        raise ValueError("must contain letters only (no numbers or special characters)")
    return s


# Every phone entering the users domain lands in E.164 (see shared/phone.py), so
# the User.phone uniqueness constraint sees one spelling of a number rather than
# several — "+15551234567" and "(555) 123-4567" must not register twice.
_validate_phone = normalize_optional_phone


def _normalize_email(v: str) -> str:
    """Lower-case an address so one mailbox has one spelling here.

    ``EmailStr`` lower-cases the *domain* only, because the local part is
    case-sensitive per RFC 5321. In practice no mail provider this platform
    serves treats it that way, and every lookup in the users service compares
    raw — so ``User@x.com`` could not log in after registering as
    ``user@x.com``, and forgot-password answered its deliberately identical
    "a reset link has been sent" while minting no token at all. The user waits
    for mail that was never sent, which is the worst of both.

    It also closes a duplicate-account hole: without this, ``A@x.com`` and
    ``a@x.com`` both satisfy the unique constraint and both deliver to the same
    person.
    """
    return v.strip().lower()


#: What a venue declares it serves. Kept in step with FOOD_TYPES in the
#: restaurants service — the value is carried there verbatim, so a spelling that
#: disagreed would be rejected only after registration had already succeeded.
FoodType = Literal["veg", "non_veg", "both"]


class RestaurantSignup(BaseModel):
    """The business a restaurant applicant is registering.

    Collected during sign-up rather than afterwards because approval gates
    login: an owner who cannot sign in cannot fill in a form later, and an
    operator approving a bare name and email would not be vetting a business at
    all. Field constraints mirror RestaurantCreate in the restaurants service,
    which is what ultimately stores this — validating here means a malformed
    address is a 422 on the form the applicant is looking at, rather than an
    event that fails silently in a consumer once they have walked away.
    """

    name: str = Field(..., min_length=1, max_length=150)
    city: str = Field(..., min_length=1, max_length=100)
    address_line: str = Field(..., min_length=1, max_length=255)
    #: The venue's public number, which is not the owner's personal one above.
    phone: str
    cuisine: str | None = Field(default=None, max_length=80)
    description: str | None = None
    food_type: FoodType = "both"

    _check_phone = field_validator("phone")(_validate_phone)


class UserRegister(BaseModel):
    """Payload for email/password registration."""

    email: EmailStr
    _lower_email = field_validator("email")(_normalize_email)
    phone: str
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=8, max_length=128)
    role: SelfServiceRole = "customer"
    #: Required for the "restaurant" role, rejected for every other one. See
    #: _restaurant_details_match_role.
    restaurant: RestaurantSignup | None = None

    _check_names = field_validator("first_name", "last_name")(_validate_name)
    _check_phone = field_validator("phone")(_validate_phone)

    @field_validator("password")
    @classmethod
    def _within_bcrypt_limit(cls, v: str) -> str:
        # bcrypt hashes at most 72 bytes; reject longer input as 422 rather
        # than letting the hash call raise a 500 downstream.
        if len(v.encode("utf-8")) > 72:
            raise ValueError("password must be at most 72 bytes")
        return v

    @model_validator(mode="after")
    def _restaurant_details_match_role(self) -> "UserRegister":
        """Business details belong to exactly one role, and are required for it.

        Required, because the restaurant record is created from this payload and
        there is no second chance to collect it — the account is inactive until
        an operator approves, so the applicant cannot log in and supply it.

        Rejected for the other roles rather than ignored: a client sending them
        has misunderstood something, and silently dropping the field would let a
        customer believe they had registered a venue.
        """
        if self.role == "restaurant":
            if self.restaurant is None:
                raise ValueError(
                    "restaurant details are required when registering as a restaurant"
                )
        elif self.restaurant is not None:
            raise ValueError(
                "restaurant details are only accepted when role is 'restaurant'"
            )
        return self


class LoginRequest(BaseModel):
    """Payload for email/password login."""

    email: EmailStr
    _lower_email = field_validator("email")(_normalize_email)
    password: str


class RefreshRequest(BaseModel):
    """Payload carrying a refresh token."""

    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    """Request a password-reset link for an email."""

    email: EmailStr
    _lower_email = field_validator("email")(_normalize_email)


class ResetPasswordRequest(BaseModel):
    """Complete a password reset with the emailed token and a new password."""

    token: str = Field(..., min_length=8)
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _within_bcrypt_limit(cls, v: str) -> str:
        if len(v.encode("utf-8")) > 72:
            raise ValueError("password must be at most 72 bytes")
        return v


class ChangePasswordRequest(BaseModel):
    """Payload for an authenticated password change."""

    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _within_bcrypt_limit(cls, v: str) -> str:
        if len(v.encode("utf-8")) > 72:
            raise ValueError("password must be at most 72 bytes")
        return v


class TokenResponse(BaseModel):
    """Issued JWT pair."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    """Public representation of a user."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    _lower_email = field_validator("email")(_normalize_email)
    phone: str
    first_name: str
    last_name: str
    role: str
    is_active: bool
    created_at: datetime


class UserUpdate(BaseModel):
    """Editable profile fields."""

    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    phone: str | None = None

    _check_names = field_validator("first_name", "last_name")(_validate_name)
    _check_phone = field_validator("phone")(_validate_phone)


class AddressCreate(BaseModel):
    """Payload to create a delivery address."""

    label: str = Field(default="home", max_length=50)
    line1: str = Field(..., min_length=1, max_length=255)
    line2: str | None = Field(default=None, max_length=255)
    city: str = Field(..., min_length=1, max_length=100)
    postal_code: str = Field(..., min_length=1, max_length=20)
    is_default: bool = False


class AddressUpdate(BaseModel):
    """Editable fields of an existing address. Omitted fields are left alone;
    ``line2`` is the one field an explicit null clears."""

    label: str | None = Field(default=None, min_length=1, max_length=50)
    line1: str | None = Field(default=None, min_length=1, max_length=255)
    line2: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, min_length=1, max_length=100)
    postal_code: str | None = Field(default=None, min_length=1, max_length=20)
    is_default: bool | None = None


class AddressResponse(BaseModel):
    """Public representation of an address."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    line1: str
    line2: str | None
    city: str
    postal_code: str
    is_default: bool
    # Null when the address has not been geocoded — the signal that it cannot be
    # placed on a map or routed to, rather than an error.
    latitude: float | None = None
    longitude: float | None = None


class AdminPasswordResetRequest(BaseModel):
    """Request to reset admin password after forced reset."""

    email: EmailStr
    _lower_email = field_validator("email")(_normalize_email)
    old_password: str = Field(..., min_length=8, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _within_bcrypt_limit(cls, v: str) -> str:
        if len(v.encode("utf-8")) > 72:
            raise ValueError("password must be at most 72 bytes")
        return v


class AdminPasswordResetResponse(BaseModel):
    """Response after admin resets password."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    _lower_email = field_validator("email")(_normalize_email)
    first_name: str
    last_name: str
    role: str
    is_active: bool
    created_at: datetime
