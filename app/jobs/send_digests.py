"""Daily send-digests cron job.

For each verified user, computes "now" in the user's local timezone and
fires every enabled task whose ``delivery_time`` (HH:MM) matches that
local time AND has ``"email"`` in ``delivery_channels``. The matched
papers go through ``select_papers_for_task`` (T13) and ``deliver_email``
(T14) — which already writes ``Delivery`` rows so future runs dedup
through T13's email-channel filter.

The whole run is wrapped in :func:`app.services.cron_log.cron_run` and
records ``digests_sent`` (count of non-empty digests delivered) into
``cron_runs.job_metadata``. Per-user / per-task failures are NOT
isolated yet — if one task explodes, the run fails and is re-runnable
once the bug is fixed (idempotence is provided by T14's unique
constraint on ``(task_id, paper_id, channel='email')``).
"""

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select

from app.db import session_scope
from app.models import Task, User
from app.services.cron_log import cron_run
from app.services.digest import deliver_email, select_papers_for_task

_UTC = ZoneInfo("UTC")


def _user_local_hh_mm(now_utc: datetime, user_tz: str) -> str:
    try:
        tz = ZoneInfo(user_tz)
    except ZoneInfoNotFoundError:
        tz = _UTC
    local = now_utc.replace(tzinfo=_UTC).astimezone(tz)
    return local.strftime("%H:%M")


async def run_send_digests() -> None:
    async with cron_run("send_digests") as meta:
        now_utc = datetime.utcnow().replace(second=0, microsecond=0)
        digests_sent = 0
        async with session_scope() as s:
            users = (await s.scalars(select(User).where(User.email_verified.is_(True)))).all()
            for user in users:
                hh_mm = _user_local_hh_mm(now_utc, user.tz)
                tasks = (
                    await s.scalars(
                        select(Task).where(
                            Task.user_id == user.id,
                            Task.enabled.is_(True),
                            Task.delivery_time == hh_mm,
                        )
                    )
                ).all()
                for task in tasks:
                    if "email" not in (task.delivery_channels or []):
                        continue
                    papers = await select_papers_for_task(s, task)
                    if not papers:
                        continue
                    await deliver_email(s, user, task, papers)
                    digests_sent += 1
        meta["digests_sent"] = digests_sent
