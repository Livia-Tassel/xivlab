"""Integration tests for the arXiv daily fetch cron job.

The job has three observable side effects:
  1. New ``papers`` rows for each fetched ArxivPaper.
  2. New ``paper_vectors`` rows (sqlite-vec virtual table) for each new paper.
  3. A ``cron_runs`` row with status='success' (or 'failed') and metadata.

These tests mock ``fetch_recent`` so no network call is made; ``embed_text``
runs against the deterministic MockBackend (default) so generated blobs are
real but reproducible.
"""

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select, text

from app.db import session_scope
from app.jobs.fetch_arxiv import run_fetch_arxiv
from app.models import CronRun, Paper
from app.services.arxiv_fetcher import ArxivPaper


def _fake_papers() -> list[ArxivPaper]:
    return [
        ArxivPaper(
            id="2401.00001",
            title="T1",
            abstract="A1",
            authors=["X"],
            primary_category="cs.AI",
            all_categories=["cs.AI"],
            published_at=datetime(2026, 5, 1, 12, 0, 0),
            pdf_url=None,
        ),
        ArxivPaper(
            id="2401.00002",
            title="T2",
            abstract="A2",
            authors=["Y"],
            primary_category="cs.LG",
            all_categories=["cs.LG"],
            published_at=datetime(2026, 5, 1, 12, 0, 0),
            pdf_url=None,
        ),
    ]


async def test_fetch_arxiv_persists_and_logs() -> None:
    with patch(
        "app.jobs.fetch_arxiv.fetch_recent",
        new=AsyncMock(return_value=_fake_papers()),
    ):
        await run_fetch_arxiv()

    async with session_scope() as s:
        papers = (await s.execute(select(Paper))).scalars().all()
        assert {p.id for p in papers} >= {"2401.00001", "2401.00002"}

        runs = (
            (await s.execute(select(CronRun).where(CronRun.job_name == "fetch_arxiv")))
            .scalars()
            .all()
        )
        assert len(runs) == 1
        run = runs[0]
        assert run.status == "success"
        assert run.error_message is None
        assert run.ended_at is not None
        assert run.started_at <= run.ended_at
        meta = run.job_metadata or {}
        assert meta.get("fetched") == 2
        assert meta.get("new_papers") == 2
        assert meta.get("embedded") == 2


async def test_fetch_arxiv_writes_paper_vectors() -> None:
    with patch(
        "app.jobs.fetch_arxiv.fetch_recent",
        new=AsyncMock(return_value=_fake_papers()),
    ):
        await run_fetch_arxiv()

    async with session_scope() as s:
        rows = (await s.execute(text("SELECT paper_id FROM paper_vectors"))).all()
        ids = {r[0] for r in rows}
        assert ids >= {"2401.00001", "2401.00002"}


async def test_fetch_arxiv_is_idempotent() -> None:
    """Re-running with the same papers must not duplicate rows nor re-embed."""
    with patch(
        "app.jobs.fetch_arxiv.fetch_recent",
        new=AsyncMock(return_value=_fake_papers()),
    ):
        await run_fetch_arxiv()
        await run_fetch_arxiv()

    async with session_scope() as s:
        papers = (await s.execute(select(Paper))).scalars().all()
        assert len(papers) == 2

        runs = (
            (await s.execute(select(CronRun).where(CronRun.job_name == "fetch_arxiv")))
            .scalars()
            .all()
        )
        assert len(runs) == 2
        # Second run sees no new papers and no new vectors.
        meta_2 = runs[1].job_metadata or {}
        assert meta_2.get("fetched") == 2
        assert meta_2.get("new_papers") == 0
        assert meta_2.get("embedded") == 0

        vec_rows = (await s.execute(text("SELECT paper_id FROM paper_vectors"))).all()
        assert len(vec_rows) == 2


async def test_fetch_arxiv_logs_failure_on_exception() -> None:
    """When fetch_recent raises, the cron_run row is marked 'failed' and the error re-raises."""

    async def _boom(*_args: object, **_kwargs: object) -> list[ArxivPaper]:
        raise RuntimeError("arxiv exploded")

    with patch("app.jobs.fetch_arxiv.fetch_recent", new=_boom):
        with pytest.raises(RuntimeError, match="arxiv exploded"):
            await run_fetch_arxiv()

    async with session_scope() as s:
        runs = (
            (await s.execute(select(CronRun).where(CronRun.job_name == "fetch_arxiv")))
            .scalars()
            .all()
        )
        assert len(runs) == 1
        run = runs[0]
        assert run.status == "failed"
        assert run.ended_at is not None
        assert run.error_message is not None
        assert "arxiv exploded" in run.error_message
