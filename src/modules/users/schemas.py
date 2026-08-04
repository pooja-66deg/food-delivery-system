"""Request/response schemas for the users domain."""

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from src.core.phone import normalize_optional_phone

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


# Every phone entering the users domain lands in E.164 (see src/core/phone.py),
# so OTP keys and the User.phone uniqueness constraint agree on one spelling.
_validate_phone = normalize_optional_phone


class UserRegister(BaseModel):
    """Payload for email/password registration."""

    email: EmailStr
    phone: str
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=8, max_length=128)
    role: SelfServiceRole = "customer"

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


class LoginRequest(BaseModel):
    """Payload for email/password login."""

    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    """Payload carrying a refresh token."""

    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    """Request a password-reset token for an email."""

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Complete a password reset with the token and a new password."""

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


class VerifyEmailRequest(BaseModel):
    """Payload carrying an email-verification token."""

    token: str = Field(..., min_length=8)


class TokenResponse(BaseModel):
    """Issued JWT pair."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class OTPRequest(BaseModel):
    """Payload to request an OTP."""

    phone: str

    _check_phone = field_validator("phone")(_validate_phone)


class OTPVerify(BaseModel):
    """Payload to verify an OTP and log in."""

    phone: str
    otp: str = Field(..., min_length=4, max_length=10)

    _check_phone = field_validator("phone")(_validate_phone)


class UserResponse(BaseModel):
    """Public representation of a user."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    phone: str
    first_name: str
    last_name: str
    role: str
    is_active: bool
    is_email_verified: bool
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
