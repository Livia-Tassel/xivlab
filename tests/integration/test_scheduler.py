"""Test the APScheduler job registration.

We don't actually start the scheduler here — that's a side-effect of the
production lifespan. We only verify that registering jobs adds the expected
ids with the expected triggers.
"""

from apscheduler.triggers.cron import CronTrigger

from app.scheduler import register_jobs, scheduler


def test_register_jobs_creates_fetch_arxiv_at_02_utc() -> None:
    # Re-registering with replace_existing=True is idempotent.
    register_jobs()
    job = scheduler.get_job("fetch_arxiv")
    assert job is not None
    trigger = job.trigger
    assert isinstance(trigger, CronTrigger)
    fields = {f.name: str(f) for f in trigger.fields}
    assert fields["hour"] == "2"
    assert fields["minute"] == "0"


def test_register_jobs_creates_send_digests_every_minute() -> None:
    register_jobs()
    job = scheduler.get_job("send_digests")
    assert job is not None
    trigger = job.trigger
    assert isinstance(trigger, CronTrigger)
    fields = {f.name: str(f) for f in trigger.fields}
    assert fields["minute"] == "*"
