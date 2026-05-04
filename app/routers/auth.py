from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.db import session_scope
from app.models import User
from app.schemas.auth import RegisterRequest, UserPublic
from app.services.password import hash_password

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest) -> UserPublic:
    async with session_scope() as s:
        existing = await s.execute(select(User).where(User.email == payload.email))
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
        user = User(
            email=str(payload.email),
            password_hash=hash_password(payload.password),
            display_name=payload.display_name,
        )
        s.add(user)
        await s.commit()
        await s.refresh(user)
        return UserPublic.model_validate(user)
