"""Integration tests for the send_digests cron job.

The job's contract:
  - Iterate over users where ``email_verified=True``.
  - For each such user, take their ``tz``, convert "now (UTC)" to that
    timezone's ``HH:MM``, and pick tasks whose ``delivery_time`` equals
    that string AND ``enabled=True`` AND ``"email" in delivery_channels``.
  - For each matched task, run ``select_papers_for_task`` + ``deliver_email``.
  - The whole run is wrapped in ``cron_run("send_digests")`` with a
    ``digests_sent`` metric.

We mock ``datetime.utcnow`` inside the job module so we control the
"now" the per-user-tz matching is computed against. We do NOT mock
``arxiv_fetcher`` here — the digest pipeline reads from already-seeded
``papers`` and ``paper_vectors`` rows, so this test is independent of
T12's fetch logic.
"""

from datetime import datetime, timedelta
from unittest.mock import patch

from sqlalchemy import select

from app.db import session_scope
from app.jobs.send_digests import run_send_digests
from app.models import CronRun, Delivery, Paper, Task, User
from app.services.email import MockEmailBackend


def _paper(pid: str, *, primary_category: str = "cs.AI") -> Paper:
    return Paper(
        id=pid,
        title=f"Title {pid}",
        abstract=f"Abstract {pid}",
        authors=["A"],
        primary_category=primary_category,
        all_categories=[primary_category],
        # 2 hours ago — well within T13's 36-hour recency window.
        published_at=datetime.utcnow() - timedelta(hours=2),
        pdf_url=None,
    )


def _task(
    user_id: int,
    *,
    name: str = "T",
    delivery_time: str = "08:00",
    enabled: bool = True,
    delivery_channels: list[str] | None = None,
    rss_token: str = "rss-",
    arxiv_categories: list[str] | None = None,
) -> Task:
    return Task(
        user_id=user_id,
        name=name,
        arxiv_categories=arxiv_categories or ["cs.AI"],
        keywords=None,
        min_keyword_match=1,
        max_papers_per_day=10,
        delivery_time=delivery_time,
        delivery_channels=delivery_channels or ["email"],
        rss_token=rss_token + "x" * (40 - len(rss_token)),
        enabled=enabled,
    )


def _patch_now(utc_dt: datetime) -> object:
    """Patch the job module's ``datetime`` so ``datetime.utcnow()`` returns ``utc_dt``."""

    class _FrozenDateTime(datetime):
        @classmethod
        def utcnow(cls) -> datetime:
            return utc_dt

    return patch("app.jobs.send_digests.datetime", _FrozenDateTime)


# --- happy path -----------------------------------------------------------


async def test_sends_digest_when_user_local_time_matches_delivery_time() -> None:
    """User in Asia/Shanghai (UTC+8); UTC=00:00 → local=08:00 → task.delivery_time=08:00 fires."""
    MockEmailBackend.reset()
    async with session_scope() as s:
        u = User(
            email="alice@x.dev",
            password_hash="x",
            email_verified=True,
            tz="Asia/Shanghai",
        )
        s.add(u)
        await s.commit()
        s.add(_task(u.id, delivery_time="08:00", rss_token="rt-shanghai-"))
        s.add(_paper("2401.00001"))
        await s.commit()
        user_id = u.id

    with _patch_now(datetime(2026, 5, 5, 0, 0, 0)):
        await run_send_digests()

    assert len(MockEmailBackend.sent) == 1
    assert MockEmailBackend.sent[0].to == "alice@x.dev"

    async with session_scope() as s:
        deliveries = (await s.scalars(select(Delivery).where(Delivery.user_id == user_id))).all()
        assert {d.paper_id for d in deliveries} == {"2401.00001"}
        assert all(d.channel == "email" for d in deliveries)


async def test_cron_run_records_digests_sent_metric() -> None:
    MockEmailBackend.reset()
    async with session_scope() as s:
        u = User(email="b@x.dev", password_hash="x", email_verified=True, tz="UTC")
        s.add(u)
        await s.commit()
        s.add(_task(u.id, delivery_time="09:00", rss_token="rt-utc-"))
        s.add(_paper("2401.00010"))
        await s.commit()

    with _patch_now(datetime(2026, 5, 5, 9, 0, 0)):
        await run_send_digests()

    async with session_scope() as s:
        runs = (await s.scalars(select(CronRun).where(CronRun.job_name == "send_digests"))).all()
        assert len(runs) == 1
        assert runs[0].status == "success"
        meta = runs[0].job_metadata or {}
        assert meta.get("digests_sent") == 1


# --- skip / filter cases --------------------------------------------------


async def test_skips_unverified_users() -> None:
    MockEmailBackend.reset()
    async with session_scope() as s:
        u = User(email="u@x.dev", password_hash="x", email_verified=False, tz="UTC")
        s.add(u)
        await s.commit()
        s.add(_task(u.id, delivery_time="09:00", rss_token="rt-unverified-"))
        s.add(_paper("2401.00020"))
        await s.commit()

    with _patch_now(datetime(2026, 5, 5, 9, 0, 0)):
        await run_send_digests()

    assert MockEmailBackend.sent == []


async def test_skips_disabled_tasks() -> None:
    MockEmailBackend.reset()
    async with session_scope() as s:
        u = User(email="u@x.dev", password_hash="x", email_verified=True, tz="UTC")
        s.add(u)
        await s.commit()
        s.add(_task(u.id, enabled=False, delivery_time="09:00", rss_token="rt-disabled-"))
        s.add(_paper("2401.00030"))
        await s.commit()

    with _patch_now(datetime(2026, 5, 5, 9, 0, 0)):
        await run_send_digests()

    assert MockEmailBackend.sent == []


async def test_skips_when_local_time_does_not_match() -> None:
    """User tz UTC, task delivery_time=08:00, but utcnow=12:00 → skip."""
    MockEmailBackend.reset()
    async with session_scope() as s:
        u = User(email="u@x.dev", password_hash="x", email_verified=True, tz="UTC")
        s.add(u)
        await s.commit()
        s.add(_task(u.id, delivery_time="08:00", rss_token="rt-mismatch-"))
        s.add(_paper("2401.00040"))
        await s.commit()

    with _patch_now(datetime(2026, 5, 5, 12, 0, 0)):
        await run_send_digests()

    assert MockEmailBackend.sent == []


async def test_skips_tasks_without_email_channel() -> None:
    MockEmailBackend.reset()
    async with session_scope() as s:
        u = User(email="u@x.dev", password_hash="x", email_verified=True, tz="UTC")
        s.add(u)
        await s.commit()
        s.add(
            _task(
                u.id,
                delivery_time="09:00",
                delivery_channels=["rss"],
                rss_token="rt-rssonly-",
            )
        )
        s.add(_paper("2401.00050"))
        await s.commit()

    with _patch_now(datetime(2026, 5, 5, 9, 0, 0)):
        await run_send_digests()

    assert MockEmailBackend.sent == []


async def test_skips_when_no_papers_match() -> None:
    """Matching delivery_time but no candidate papers → no email, no Delivery rows."""
    MockEmailBackend.reset()
    async with session_scope() as s:
        u = User(email="u@x.dev", password_hash="x", email_verified=True, tz="UTC")
        s.add(u)
        await s.commit()
        # Task wants cs.LG; the only paper is cs.AI → no match.
        s.add(
            _task(
                u.id,
                delivery_time="09:00",
                arxiv_categories=["cs.LG"],
                rss_token="rt-empty-",
            )
        )
        s.add(_paper("2401.00060", primary_category="cs.AI"))
        await s.commit()

    with _patch_now(datetime(2026, 5, 5, 9, 0, 0)):
        await run_send_digests()

    assert MockEmailBackend.sent == []
    async with session_scope() as s:
        rows = (await s.scalars(select(Delivery))).all()
        assert rows == []


async def test_falls_back_to_utc_when_user_tz_is_invalid() -> None:
    """Bad tz string shouldn't crash the job — treat as UTC."""
    MockEmailBackend.reset()
    async with session_scope() as s:
        u = User(
            email="u@x.dev",
            password_hash="x",
            email_verified=True,
            tz="Not/A_Real_Zone",
        )
        s.add(u)
        await s.commit()
        # delivery_time set to "09:00" — matches utcnow=09:00 only if fallback to UTC works.
        s.add(_task(u.id, delivery_time="09:00", rss_token="rt-badtz-"))
        s.add(_paper("2401.00070"))
        await s.commit()

    with _patch_now(datetime(2026, 5, 5, 9, 0, 0)):
        await run_send_digests()

    assert len(MockEmailBackend.sent) == 1


async def test_two_users_in_different_timezones_both_fire_at_same_utc() -> None:
    """At UTC=00:00, Asia/Shanghai user (UTC+8) sees 08:00 local; UTC user sees 00:00. Both with matching tasks should fire."""
    MockEmailBackend.reset()
    async with session_scope() as s:
        u1 = User(
            email="sh@x.dev",
            password_hash="x",
            email_verified=True,
            tz="Asia/Shanghai",
        )
        u2 = User(email="utc@x.dev", password_hash="x", email_verified=True, tz="UTC")
        s.add_all([u1, u2])
        await s.commit()
        s.add(_task(u1.id, delivery_time="08:00", rss_token="rt-sh-"))
        s.add(_task(u2.id, delivery_time="00:00", rss_token="rt-utc2-"))
        s.add(_paper("2401.00080"))
        await s.commit()

    with _patch_now(datetime(2026, 5, 5, 0, 0, 0)):
        await run_send_digests()

    recipients = {m.to for m in MockEmailBackend.sent}
    assert recipients == {"sh@x.dev", "utc@x.dev"}
