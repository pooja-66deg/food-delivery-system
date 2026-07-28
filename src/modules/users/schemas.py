"""Request/response schemas for the users domain."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# Roles a user may self-register as. "admin" is provisioned separately, never
# via public registration.
SelfServiceRole = Literal["customer", "restaurant"]


class UserRegister(BaseModel):
    """Payload for email/password registration."""

    email: EmailStr
    phone: str = Field(..., min_length=8, max_length=20)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=8, max_length=128)
    role: SelfServiceRole = "customer"


class LoginRequest(BaseModel):
    """Payload for email/password login."""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Issued JWT pair."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class OTPRequest(BaseModel):
    """Payload to request an OTP."""

    phone: str = Field(..., min_length=8, max_length=20)


class OTPVerify(BaseModel):
    """Payload to verify an OTP and log in."""

    phone: str = Field(..., min_length=8, max_length=20)
    otp: str = Field(..., min_length=4, max_length=10)


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
    created_at: datetime


class UserUpdate(BaseModel):
    """Editable profile fields."""

    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    phone: str | None = Field(default=None, min_length=8, max_length=20)


class AddressCreate(BaseModel):
    """Payload to create a delivery address."""

    label: str = Field(default="home", max_length=50)
    line1: str = Field(..., min_length=1, max_length=255)
    line2: str | None = Field(default=None, max_length=255)
    city: str = Field(..., min_length=1, max_length=100)
    postal_code: str = Field(..., min_length=1, max_length=20)
    is_default: bool = False


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
