from fastapi import APIRouter, Cookie, HTTPException, Request, Response, status
from sqlalchemy import select

from app.db import session_scope
from app.deps import COOKIE_NAME
from app.models import User
from app.schemas.auth import LoginRequest, RegisterRequest, UserPublic
from app.services.password import hash_password, verify_password
from app.services.session import (
    SESSION_LIFETIME,
    create_session,
    delete_session,
)

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


@router.post("/login")
async def login(payload: LoginRequest, response: Response, request: Request) -> dict[str, bool]:
    async with session_scope() as s:
        result = await s.execute(select(User).where(User.email == payload.email))
        user = result.scalar_one_or_none()
        if user is None or not verify_password(payload.password, user.password_hash):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bad credentials")
        sess = await create_session(
            s,
            user,
            user_agent=request.headers.get("user-agent"),
            ip=request.client.host if request.client is not None else None,
        )

    response.set_cookie(
        COOKIE_NAME,
        sess.id,
        httponly=True,
        samesite="lax",
        secure=False,  # set True in prod via APP_ENV check (TODO once deploy lands)
        max_age=int(SESSION_LIFETIME.total_seconds()),
    )
    return {"ok": True}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    session: str | None = Cookie(default=None, alias=COOKIE_NAME),
) -> Response:
    if session:
        async with session_scope() as s:
            await delete_session(s, session)
    response.delete_cookie(COOKIE_NAME)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
