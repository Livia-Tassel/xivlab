"""Pre-render per-task RSS feeds to ``DATA_DIR / rss_cache`` for cheap reads.

Reading the disk file from the route handler isn't wired up yet — this job
exists so feeds are warm and so we have a migration path off live DB reads
when traffic grows. For now it's a write-only artifact.
"""

from datetime import datetime, timedelta

from sqlalchemy import select

from app.config import DATA_DIR, get_settings
from app.db import session_scope
from app.models import Delivery, Paper, Task
from app.services.cron_log import cron_run
from app.services.feed_renderer import render_atom

FEED_WINDOW_DAYS: int = 30
FEED_MAX_ENTRIES: int = 50


async def run_refresh_rss() -> None:
    async with cron_run("refresh_rss") as meta:
        cache_dir = DATA_DIR / "rss_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        base_url = get_settings().app_base_url

        written = 0
        async with session_scope() as s:
            tasks = list((await s.scalars(select(Task).where(Task.enabled.is_(True)))).all())
            for task in tasks:
                cutoff = datetime.utcnow() - timedelta(days=FEED_WINDOW_DAYS)
                papers = list(
                    (
                        await s.scalars(
                            select(Paper)
                            .join(Delivery, Delivery.paper_id == Paper.id)
                            .where(
                                Delivery.task_id == task.id,
                                Delivery.delivered_at >= cutoff,
                            )
                            .order_by(Paper.published_at.desc())
                            .limit(FEED_MAX_ENTRIES)
                        )
                    ).all()
                )
                xml = render_atom(task, papers, base_url=base_url, user_id=task.user_id)
                target = cache_dir / f"{task.user_id}_{task.id}.xml"
                target.write_text(xml, encoding="utf-8")
                written += 1
        meta["feeds_written"] = written
