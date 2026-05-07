"""APScheduler wiring: register cron jobs and expose the singleton scheduler.

The scheduler is created at import time but not started — :func:`register_jobs`
registers the per-job cron triggers, and the FastAPI lifespan hook in
``app.main`` is responsible for ``start()`` / ``shutdown()`` so jobs only fire
inside a live app process (not in tests, not in scripts).
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.jobs.backup import run_backup
from app.jobs.cleanup import run_cleanup
from app.jobs.fetch_arxiv import run_fetch_arxiv
from app.jobs.refresh_rss import run_refresh_rss
from app.jobs.send_digests import run_send_digests

scheduler = AsyncIOScheduler(timezone="UTC")


def register_jobs() -> None:
    scheduler.add_job(
        run_fetch_arxiv,
        CronTrigger(hour=2, minute=0),
        id="fetch_arxiv",
        replace_existing=True,
    )
    scheduler.add_job(
        run_send_digests,
        CronTrigger(minute="*"),
        id="send_digests",
        replace_existing=True,
    )
    scheduler.add_job(
        run_backup,
        CronTrigger(hour=4, minute=0),
        id="backup",
        replace_existing=True,
    )
    scheduler.add_job(
        run_cleanup,
        CronTrigger(hour=4, minute=30),
        id="cleanup",
        replace_existing=True,
    )
    scheduler.add_job(
        run_refresh_rss,
        CronTrigger(minute="*/15"),
        id="refresh_rss",
        replace_existing=True,
    )
