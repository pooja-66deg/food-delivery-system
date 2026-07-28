"""HTTP routes for the users domain (auth + profile)."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.infrastructure.database import get_db
from src.infrastructure.redis import get_redis
from src.modules.users import otp as otp_module
from src.modules.users import profile as profile_service
from src.modules.users import service
from src.modules.users.dependencies import get_current_user
from src.modules.users.models import User
from src.modules.users.schemas import (
    AddressCreate,
    AddressResponse,
    LoginRequest,
    OTPRequest,
    OTPVerify,
    TokenResponse,
    UserRegister,
    UserResponse,
    UserUpdate,
)

auth_router = APIRouter(prefix="/auth", tags=["auth"])
users_router = APIRouter(prefix="/users", tags=["users"])


@auth_router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(data: UserRegister, session: AsyncSession = Depends(get_db)):
    return await service.register_user(session, data)


@auth_router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, session: AsyncSession = Depends(get_db)):
    return await service.login(session, data.email, data.password)


@auth_router.post("/otp/request")
async def request_otp(data: OTPRequest, redis=Depends(get_redis)):
    code = await otp_module.request_otp(redis, data.phone)
    body = {"message": "OTP sent"}
    # Convenience for local/dev and tests; never exposed in production.
    if settings.environment != "production":
        body["debug_otp"] = code
    return body


@auth_router.post("/otp/verify", response_model=TokenResponse)
async def verify_otp(data: OTPVerify, session: AsyncSession = Depends(get_db), redis=Depends(get_redis)):
    return await service.login_with_otp(session, redis, data.phone, data.otp)


@users_router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@users_router.patch("/me", response_model=UserResponse)
async def update_me(
    data: UserUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    return await profile_service.update_profile(session, current_user, data)


@users_router.get("/me/addresses", response_model=list[AddressResponse])
async def list_addresses(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    return await profile_service.list_addresses(session, current_user)


@users_router.post("/me/addresses", response_model=AddressResponse, status_code=status.HTTP_201_CREATED)
async def add_address(
    data: AddressCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    return await profile_service.add_address(session, current_user, data)


@users_router.delete("/me/addresses/{address_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_address(
    address_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await profile_service.delete_address(session, current_user, address_id)
