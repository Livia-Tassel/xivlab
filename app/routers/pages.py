"""Server-rendered HTML pages backed by Jinja2 + HTMX.

The pages here orchestrate the auth services directly (rather than calling
the JSON API endpoints) so that error rendering, redirects, and cookies
are all idiomatic FastAPI ``Response`` constructions.
"""

from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Cookie, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from app.config import PROJECT_ROOT, get_settings
from app.db import session_scope
from app.deps import COOKIE_NAME, current_user
from app.models import (
    EmailVerificationToken,
    PasswordResetToken,
    User,
)
from app.services.email import send_email
from app.services.password import hash_password, verify_password
from app.services.session import SESSION_LIFETIME, create_session
from app.services.tokens import random_token

templates = Jinja2Templates(directory=str(PROJECT_ROOT / "templates"))
router = APIRouter()

VERIFY_TOKEN_LIFETIME = timedelta(hours=48)
PASSWORD_RESET_LIFETIME = timedelta(hours=48)


async def _try_user(session_token: str | None) -> User | None:
    """Best-effort: return the User for a session cookie, or None if missing/expired."""
    if not session_token:
        return None
    try:
        return await current_user(session=session_token)
    except Exception:  # expected: HTTPException(401) from current_user
        return None


# --- Login -----------------------------------------------------------------


@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> Response:
    user = await _try_user(session)
    return templates.TemplateResponse(request, "auth/login.html", {"user": user})


@router.post("/login")
async def login_submit(
    request: Request,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
) -> Response:
    async with session_scope() as s:
        user = (await s.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if user is None or not verify_password(password, user.password_hash):
            return templates.TemplateResponse(
                request,
                "auth/login.html",
                {"user": None, "error": "Bad credentials"},
                status_code=401,
            )
        sess = await create_session(
            s,
            user,
            user_agent=request.headers.get("user-agent"),
            ip=request.client.host if request.client is not None else None,
        )

    redirect = RedirectResponse("/dashboard", status_code=303)
    redirect.set_cookie(
        COOKIE_NAME,
        sess.id,
        httponly=True,
        samesite="lax",
        secure=False,  # TODO flip in prod via APP_ENV
        max_age=int(SESSION_LIFETIME.total_seconds()),
    )
    return redirect


# --- Register --------------------------------------------------------------


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request) -> Response:
    return templates.TemplateResponse(request, "auth/register.html", {"user": None})


@router.post("/register")
async def register_submit(
    request: Request,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    display_name: Annotated[str | None, Form()] = None,
) -> Response:
    if len(password) < 8:
        return templates.TemplateResponse(
            request,
            "auth/register.html",
            {"user": None, "error": "Password must be at least 8 characters"},
            status_code=422,
        )

    display_name_clean = (display_name or "").strip() or None

    async with session_scope() as s:
        existing = (await s.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if existing is not None:
            return templates.TemplateResponse(
                request,
                "auth/register.html",
                {"user": None, "error": "Email already registered"},
                status_code=409,
            )
        user = User(
            email=email,
            password_hash=hash_password(password),
            display_name=display_name_clean,
        )
        s.add(user)
        await s.flush()
        token_value = random_token(32)
        s.add(
            EmailVerificationToken(
                token=token_value,
                user_id=user.id,
                expires_at=datetime.utcnow() + VERIFY_TOKEN_LIFETIME,
            )
        )
        await s.commit()

    settings = get_settings()
    verify_url = f"{settings.app_base_url}/verify-email/{token_value}"
    await send_email(
        to=email,
        subject="[xivLab] Verify your email",
        html=(
            "<p>Welcome to xivLab! Confirm your email by clicking: "
            f'<a href="{verify_url}">{verify_url}</a></p>'
        ),
        text=f"Welcome to xivLab! Confirm your email: {verify_url}",
    )

    return RedirectResponse(f"/verify-pending?email={email}", status_code=303)


@router.get("/verify-pending", response_class=HTMLResponse)
async def verify_pending_page(request: Request, email: str | None = None) -> Response:
    return templates.TemplateResponse(
        request, "auth/verify_pending.html", {"user": None, "email": email}
    )


# --- Email verification (link landing) -------------------------------------


@router.get("/verify-email/{token}", response_class=HTMLResponse)
async def verify_email_page(request: Request, token: str) -> Response:
    """Landing page for the verification link in the user's inbox.

    Consumes the token immediately on GET — same one-shot semantics as the
    JSON API. Renders a success or failure page accordingly.
    """
    ok = False
    async with session_scope() as s:
        evt = (
            await s.execute(
                select(EmailVerificationToken).where(EmailVerificationToken.token == token)
            )
        ).scalar_one_or_none()
        if evt is not None and evt.used_at is None and evt.expires_at >= datetime.utcnow():
            user = (await s.execute(select(User).where(User.id == evt.user_id))).scalar_one()
            user.email_verified = True
            evt.used_at = datetime.utcnow()
            await s.commit()
            ok = True
    return templates.TemplateResponse(
        request,
        "auth/verify_result.html",
        {"user": None, "ok": ok},
        status_code=200 if ok else 410,
    )


# --- Forgot / reset password -----------------------------------------------


@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request) -> Response:
    return templates.TemplateResponse(
        request, "auth/forgot_password.html", {"user": None, "sent": False}
    )


@router.post("/forgot-password")
async def forgot_password_submit(request: Request, email: Annotated[str, Form()]) -> Response:
    token_value: str | None = None
    user_email: str | None = None
    async with session_scope() as s:
        user = (await s.execute(select(User).where(User.email == email))).scalar_one_or_none()
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
            text=f"Click the link to reset your password: {url}\nThis link expires in 48 hours.",
        )

    return templates.TemplateResponse(
        request, "auth/forgot_password.html", {"user": None, "sent": True}
    )


@router.get("/reset-password/{token}", response_class=HTMLResponse)
async def reset_password_page(request: Request, token: str) -> Response:
    return templates.TemplateResponse(
        request,
        "auth/reset_password.html",
        {"user": None, "token": token, "done": False},
    )


@router.post("/reset-password")
async def reset_password_submit(
    request: Request,
    token: Annotated[str, Form()],
    new_password: Annotated[str, Form()],
) -> Response:
    if len(new_password) < 8:
        return templates.TemplateResponse(
            request,
            "auth/reset_password.html",
            {
                "user": None,
                "token": token,
                "done": False,
                "error": "Password must be at least 8 characters",
            },
            status_code=422,
        )

    async with session_scope() as s:
        tok = (
            await s.execute(select(PasswordResetToken).where(PasswordResetToken.token == token))
        ).scalar_one_or_none()
        if tok is None or tok.used_at is not None or tok.expires_at < datetime.utcnow():
            return templates.TemplateResponse(
                request,
                "auth/reset_password.html",
                {
                    "user": None,
                    "token": token,
                    "done": False,
                    "error": "Invalid or expired token",
                },
                status_code=404,
            )
        user = (await s.execute(select(User).where(User.id == tok.user_id))).scalar_one()
        user.password_hash = hash_password(new_password)
        tok.used_at = datetime.utcnow()
        await s.commit()

    return templates.TemplateResponse(
        request, "auth/reset_password.html", {"user": None, "token": token, "done": True}
    )
