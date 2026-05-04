"""FastAPI dependency callables shared across routers."""

from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy import select

from app.db import session_scope
from app.models import User
from app.services.session import get_session, slide_session

COOKIE_NAME: str = "session"


async def current_user(
    session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> User:
    """Resolve the authenticated user from the session cookie.

    Raises 401 if the cookie is missing or the session is expired/missing.
    Slides the session forward (rolling expiry) on every authenticated request.
    """
    if not session:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    async with session_scope() as s:
        sess = await get_session(s, session)
        if sess is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
        await slide_session(s, sess)
        user = (await s.execute(select(User).where(User.id == sess.user_id))).scalar_one()
        return user


async def require_admin(user: Annotated[User, Depends(current_user)]) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin only")
    return user


async def require_email_verified(user: Annotated[User, Depends(current_user)]) -> User:
    if not user.email_verified:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Email not verified")
    return user
