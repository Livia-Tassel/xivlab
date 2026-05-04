from typing import Annotated

from fastapi import APIRouter, Depends

from app.deps import current_user
from app.models import User
from app.schemas.auth import UserPublic

router = APIRouter(prefix="/api/v1/me", tags=["me"])


@router.get("", response_model=UserPublic)
async def me(user: Annotated[User, Depends(current_user)]) -> UserPublic:
    return UserPublic.model_validate(user)
