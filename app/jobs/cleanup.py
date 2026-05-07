"""Daily cleanup job.

Removes:
  * expired sessions (``expires_at < now``)
  * used or expired email-verification tokens
  * used or expired password-reset tokens
  * cron_runs rows older than ``CRON_RETENTION_DAYS``
"""

from datetime import datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.engine import CursorResult

from app.db import session_scope
from app.models import CronRun, EmailVerificationToken, PasswordResetToken, Session
from app.services.cron_log import cron_run

CRON_RETENTION_DAYS: int = 30


async def run_cleanup() -> None:
    async with cron_run("cleanup") as meta:
        now = datetime.utcnow()
        cron_cutoff = now - timedelta(days=CRON_RETENTION_DAYS)

        async with session_scope() as s:
            sess_res: CursorResult = await s.execute(  # type: ignore[assignment]
                delete(Session).where(Session.expires_at < now)
            )
            evt_res: CursorResult = await s.execute(  # type: ignore[assignment]
                delete(EmailVerificationToken).where(
                    (EmailVerificationToken.used_at.is_not(None))
                    | (EmailVerificationToken.expires_at < now)
                )
            )
            prt_res: CursorResult = await s.execute(  # type: ignore[assignment]
                delete(PasswordResetToken).where(
                    (PasswordResetToken.used_at.is_not(None))
                    | (PasswordResetToken.expires_at < now)
                )
            )
            cron_res: CursorResult = await s.execute(  # type: ignore[assignment]
                delete(CronRun).where(CronRun.started_at < cron_cutoff)
            )
            await s.commit()

        meta["expired_sessions"] = sess_res.rowcount or 0
        meta["expired_verify_tokens"] = evt_res.rowcount or 0
        meta["expired_reset_tokens"] = prt_res.rowcount or 0
        meta["old_cron_runs"] = cron_res.rowcount or 0
