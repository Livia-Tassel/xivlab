"""Tests for backup + cleanup + refresh_rss jobs."""

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app.db import session_scope
from app.jobs.cleanup import run_cleanup
from app.jobs.refresh_rss import run_refresh_rss
from app.models import (
    CronRun,
    Delivery,
    EmailVerificationToken,
    Paper,
    PasswordResetToken,
    Session,
    Task,
    User,
)
from app.services.password import hash_password

# --- backup --------------------------------------------------------------


@pytest.mark.asyncio
async def test_backup_creates_dated_file_and_logs_run(tmp_path, monkeypatch) -> None:
    """Backup writes a snapshot under DATA_DIR/backups and pruning is logged."""
    # Point DATA_DIR at a writable temp location for this test.
    from app import config as app_config
    from app.jobs import backup as backup_mod

    monkeypatch.setattr(app_config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(backup_mod, "DATA_DIR", tmp_path)

    # Stand up a tiny SQLite file so `sqlite3 .backup` has something to copy.
    src_db = tmp_path / "src.db"
    import sqlite3

    sqlite3.connect(str(src_db)).close()
    monkeypatch.setattr(backup_mod, "_resolve_db_path", lambda: src_db)

    await backup_mod.run_backup()

    backups = list((tmp_path / "backups").glob("*.db"))
    assert len(backups) == 1
    today = datetime.utcnow().strftime("%Y-%m-%d")
    assert backups[0].name == f"{today}.db"

    async with session_scope() as s:
        runs = list((await s.scalars(select(CronRun).where(CronRun.job_name == "backup"))).all())
        assert len(runs) == 1
        assert runs[0].status == "success"


@pytest.mark.asyncio
async def test_backup_prunes_old_files(tmp_path, monkeypatch) -> None:
    from app import config as app_config
    from app.jobs import backup as backup_mod

    monkeypatch.setattr(app_config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(backup_mod, "DATA_DIR", tmp_path)

    src_db = tmp_path / "src.db"
    import sqlite3

    sqlite3.connect(str(src_db)).close()
    monkeypatch.setattr(backup_mod, "_resolve_db_path", lambda: src_db)

    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    old = backup_dir / "2020-01-01.db"
    old.write_bytes(b"")
    # Force mtime to 30 days ago — well past 14-day retention.
    import os

    long_ago = datetime.utcnow().timestamp() - 30 * 86400
    os.utime(old, (long_ago, long_ago))

    await backup_mod.run_backup()
    assert not old.exists()


# --- cleanup -------------------------------------------------------------


@pytest.mark.asyncio
async def test_cleanup_deletes_expired_sessions_and_tokens() -> None:
    now = datetime.utcnow()
    async with session_scope() as s:
        u = User(email="c@x.dev", password_hash=hash_password("p"), email_verified=True)
        s.add(u)
        await s.flush()

        # Expired session
        s.add(
            Session(
                id="expired-session-id",
                user_id=u.id,
                expires_at=now - timedelta(hours=1),
            )
        )
        # Live session
        s.add(
            Session(
                id="live-session-id",
                user_id=u.id,
                expires_at=now + timedelta(days=7),
            )
        )
        # Used verify token
        s.add(
            EmailVerificationToken(
                token="tk-used",
                user_id=u.id,
                expires_at=now + timedelta(days=1),
                used_at=now - timedelta(minutes=1),
            )
        )
        # Expired verify token
        s.add(
            EmailVerificationToken(
                token="tk-expired",
                user_id=u.id,
                expires_at=now - timedelta(days=1),
            )
        )
        # Live verify token
        s.add(
            EmailVerificationToken(
                token="tk-live",
                user_id=u.id,
                expires_at=now + timedelta(days=1),
            )
        )
        # Used reset token
        s.add(
            PasswordResetToken(
                token="rt-used",
                user_id=u.id,
                expires_at=now + timedelta(days=1),
                used_at=now - timedelta(minutes=1),
            )
        )
        # Old cron run (>30 days)
        s.add(
            CronRun(
                job_name="fetch_arxiv",
                started_at=now - timedelta(days=40),
                status="success",
                job_metadata={},
            )
        )
        # Recent cron run
        s.add(
            CronRun(
                job_name="fetch_arxiv",
                started_at=now - timedelta(days=2),
                status="success",
                job_metadata={},
            )
        )
        await s.commit()

    await run_cleanup()

    async with session_scope() as s:
        sessions = list((await s.scalars(select(Session))).all())
        assert {x.id for x in sessions} == {"live-session-id"}
        evts = list((await s.scalars(select(EmailVerificationToken))).all())
        assert {x.token for x in evts} == {"tk-live"}
        rts = list((await s.scalars(select(PasswordResetToken))).all())
        assert rts == []
        runs = list(
            (await s.scalars(select(CronRun).where(CronRun.job_name == "fetch_arxiv"))).all()
        )
        # Only the recent run survived (cleanup's own run is "cleanup", not "fetch_arxiv").
        assert len(runs) == 1


# --- refresh_rss --------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_rss_writes_per_task_xml(tmp_path, monkeypatch) -> None:
    from app import config as app_config
    from app.jobs import refresh_rss as refresh_mod

    monkeypatch.setattr(app_config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(refresh_mod, "DATA_DIR", tmp_path)

    async with session_scope() as s:
        u = User(email="rss@x.dev", password_hash=hash_password("p"), email_verified=True)
        s.add(u)
        await s.flush()
        t = Task(
            user_id=u.id,
            name="Daily LLM",
            arxiv_categories=["cs.AI"],
            keywords=None,
            min_keyword_match=1,
            interest_description=None,
            max_papers_per_day=10,
            delivery_time="08:00",
            delivery_channels=["rss"],
            rss_token="tok123",
            enabled=True,
        )
        s.add(t)
        await s.flush()
        p = Paper(
            id="2401.00001",
            title="A Paper",
            authors=["Alice"],
            abstract="Abstract here",
            primary_category="cs.AI",
            all_categories=["cs.AI"],
            published_at=datetime.utcnow(),
        )
        s.add(p)
        s.add(
            Delivery(
                user_id=u.id,
                task_id=t.id,
                paper_id=p.id,
                delivered_at=datetime.utcnow(),
                channel="rss",
            )
        )
        await s.commit()
        uid, tid = u.id, t.id

    await run_refresh_rss()

    expected = tmp_path / "rss_cache" / f"{uid}_{tid}.xml"
    assert expected.exists()
    body = expected.read_text()
    assert "<feed" in body
    assert "A Paper" in body


@pytest.mark.asyncio
async def test_refresh_rss_skips_disabled_tasks(tmp_path, monkeypatch) -> None:
    from app import config as app_config
    from app.jobs import refresh_rss as refresh_mod

    monkeypatch.setattr(app_config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(refresh_mod, "DATA_DIR", tmp_path)

    async with session_scope() as s:
        u = User(email="off@x.dev", password_hash=hash_password("p"), email_verified=True)
        s.add(u)
        await s.flush()
        s.add(
            Task(
                user_id=u.id,
                name="Disabled",
                arxiv_categories=["cs.AI"],
                min_keyword_match=1,
                max_papers_per_day=10,
                delivery_time="08:00",
                delivery_channels=["rss"],
                rss_token="off-tok",
                enabled=False,
            )
        )
        await s.commit()

    await run_refresh_rss()

    cache = tmp_path / "rss_cache"
    assert cache.exists()
    assert list(cache.glob("*.xml")) == []


def test_scheduler_registers_backup_cleanup_refresh_rss() -> None:
    from app.scheduler import register_jobs, scheduler

    register_jobs()
    assert scheduler.get_job("backup") is not None
    assert scheduler.get_job("cleanup") is not None
    assert scheduler.get_job("refresh_rss") is not None


# Suppress unused warnings for tmp_path usage type checker
_ = Path
