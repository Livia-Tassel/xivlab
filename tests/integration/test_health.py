"""Tests for the /health endpoint."""

from datetime import datetime

from httpx import AsyncClient

from app.db import session_scope
from app.models import CronRun


async def test_health_returns_ok_db_field(client: AsyncClient) -> None:
    r = await client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"


async def test_health_last_arxiv_run_null_when_no_runs(client: AsyncClient) -> None:
    r = await client.get("/health")
    assert r.json()["last_arxiv_run"] is None


async def test_health_last_arxiv_run_includes_latest(client: AsyncClient) -> None:
    async with session_scope() as s:
        s.add_all(
            [
                CronRun(
                    job_name="fetch_arxiv",
                    started_at=datetime(2026, 5, 4, 2, 0, 0),
                    ended_at=datetime(2026, 5, 4, 2, 0, 30),
                    status="success",
                    job_metadata={"new": 10},
                ),
                CronRun(
                    job_name="fetch_arxiv",
                    started_at=datetime(2026, 5, 5, 2, 0, 0),
                    ended_at=datetime(2026, 5, 5, 2, 0, 25),
                    status="success",
                    job_metadata={"new": 7},
                ),
                CronRun(
                    job_name="other_job",
                    started_at=datetime(2026, 5, 6, 0, 0, 0),
                    status="success",
                    job_metadata={},
                ),
            ]
        )
        await s.commit()

    r = await client.get("/health")
    assert r.status_code == 200
    body = r.json()
    # Should pick the most recent fetch_arxiv run, not other_job.
    assert body["last_arxiv_run"] is not None
    assert body["last_arxiv_run"].startswith("2026-05-05")
