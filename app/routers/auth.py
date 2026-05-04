from datetime import datetime, timedelta

from fastapi import APIRouter, Cookie, HTTPException, Request, Response, status
from sqlalchemy import select

from app.config import get_settings
from app.db import session_scope
from app.deps import COOKIE_NAME
from app.models import EmailVerificationToken, PasswordResetToken, User
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    UserPublic,
)
from app.services.email import send_email
from app.services.password import hash_password, verify_password
from app.services.session import SESSION_LIFETIME, create_session, delete_session
from app.services.tokens import random_token

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

VERIFY_TOKEN_LIFETIME = timedelta(hours=48)
PASSWORD_RESET_LIFETIME = timedelta(hours=48)


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
        await s.flush()  # populate user.id for the token FK

        token_value = random_token(32)
        s.add(
            EmailVerificationToken(
                token=token_value,
                user_id=user.id,
                expires_at=datetime.utcnow() + VERIFY_TOKEN_LIFETIME,
            )
        )
        await s.commit()
        await s.refresh(user)
        public = UserPublic.model_validate(user)

    settings = get_settings()
    verify_url = f"{settings.app_base_url}/verify-email/{token_value}"
    await send_email(
        to=public.email,
        subject="[xivLab] Verify your email",
        html=(
            "<p>Welcome to xivLab! Confirm your email by clicking: "
            f'<a href="{verify_url}">{verify_url}</a></p>'
        ),
        text=f"Welcome to xivLab! Confirm your email: {verify_url}",
    )
    return public


@router.post("/verify-email/{token}")
async def verify_email(token: str) -> dict[str, bool]:
    async with session_scope() as s:
        evt = (
            await s.execute(
                select(EmailVerificationToken).where(EmailVerificationToken.token == token)
            )
        ).scalar_one_or_none()
        if evt is None or evt.used_at is not None or evt.expires_at < datetime.utcnow():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Invalid or expired token")
        user = (await s.execute(select(User).where(User.id == evt.user_id))).scalar_one()
        user.email_verified = True
        evt.used_at = datetime.utcnow()
        await s.commit()
    return {"ok": True}


@router.post("/forgot-password")
async def forgot_password(payload: ForgotPasswordRequest) -> dict[str, bool]:
    """Request a password reset link.

    Always returns 200 — even when the email isn't registered — to avoid
    leaking which emails have accounts (anti-enumeration). When the email
    DOES exist, a reset token is created and a reset email dispatched.
    """
    token_value: str | None = None
    user_email: str | None = None
    async with session_scope() as s:
        user = (
            await s.execute(select(User).where(User.email == payload.email))
        ).scalar_one_or_none()
        if user is not None:
            token_value = random_token(32)
            s.add(
                PasswordResetToken(
                    token=token_value,
                    user_id=user.id,
                    expires_at=datetime.utcnow() + PASSWORD_RESET_LIFETIME,
                )
            )
            await s.commit()
            user_email = user.email

    if token_value is not None and user_email is not None:
        settings = get_settings()
        url = f"{settings.app_base_url}/reset-password/{token_value}"
        await send_email(
            to=user_email,
            subject="[xivLab] Reset your password",
            html=(
                "<p>Click the link to reset your password: "
                f'<a href="{url}">{url}</a>. '
                "This link expires in 48 hours.</p>"
            ),
            text=(f"Click the link to reset your password: {url}\nThis link expires in 48 hours."),
        )

    return {"ok": True}


@router.post("/reset-password")
async def reset_password(payload: ResetPasswordRequest) -> dict[str, bool]:
    async with session_scope() as s:
        tok = (
            await s.execute(
                select(PasswordResetToken).where(PasswordResetToken.token == payload.token)
            )
        ).scalar_one_or_none()
        if tok is None or tok.used_at is not None or tok.expires_at < datetime.utcnow():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Invalid or expired token")
        user = (await s.execute(select(User).where(User.id == tok.user_id))).scalar_one()
        user.password_hash = hash_password(payload.new_password)
        tok.used_at = datetime.utcnow()
        await s.commit()
    return {"ok": True}


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
