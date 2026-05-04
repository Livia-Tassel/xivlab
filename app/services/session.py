"""Session service: create / lookup / extend / delete server-side sessions."""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Session as DbSession
from app.models import User
from app.services.tokens import random_token

SESSION_LIFETIME = timedelta(days=30)


async def create_session(
    s: AsyncSession,
    user: User,
    *,
    user_agent: str | None = None,
    ip: str | None = None,
) -> DbSession:
    """Create and persist a fresh session row for ``user``."""
    sid = random_token(32)
    now = datetime.utcnow()
    sess = DbSession(
        id=sid,
        user_id=user.id,
        expires_at=now + SESSION_LIFETIME,
        last_seen_at=now,
        user_agent=user_agent,
        ip=ip,
    )
    s.add(sess)
    await s.commit()
    return sess


async def get_session(s: AsyncSession, sid: str) -> DbSession | None:
    """Return the session row for ``sid`` if it exists and hasn't expired."""
    result = await s.execute(select(DbSession).where(DbSession.id == sid))
    sess = result.scalar_one_or_none()
    if sess is None or sess.expires_at < datetime.utcnow():
        return None
    return sess


async def delete_session(s: AsyncSession, sid: str) -> None:
    """Best-effort delete; no-op if the session is already gone."""
    result = await s.execute(select(DbSession).where(DbSession.id == sid))
    sess = result.scalar_one_or_none()
    if sess is not None:
        await s.delete(sess)
        await s.commit()


async def slide_session(s: AsyncSession, sess: DbSession) -> None:
    """Extend the session — moves expires_at and last_seen_at forward."""
    now = datetime.utcnow()
    sess.expires_at = now + SESSION_LIFETIME
    sess.last_seen_at = now
    await s.commit()
