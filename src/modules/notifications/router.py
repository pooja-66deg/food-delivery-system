"""HTTP routes for notifications."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database import get_db
from src.modules.notifications import service
from src.modules.notifications.schemas import NotificationRead
from src.modules.users.dependencies import get_current_user
from src.modules.users.models import User

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationRead])
async def list_my_notifications(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db)
):
    return await service.list_for_user(session, user.id)
