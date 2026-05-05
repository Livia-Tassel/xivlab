"""Cron job execution logging.

Wraps an async block in a ``cron_runs`` row tracking lifecycle:
inserts a 'running' row on enter, flips to 'success' or 'failed' on exit,
and persists arbitrary per-job metrics through the yielded mutable dict.

Usage::

    async with cron_run("fetch_arxiv") as meta:
        ...
        meta["new_papers"] = 17
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from app.db import session_scope
from app.models import CronRun


@asynccontextmanager
async def cron_run(job_name: str) -> AsyncIterator[dict[str, Any]]:
    async with session_scope() as s:
        row = CronRun(
            job_name=job_name,
            started_at=datetime.utcnow(),
            status="running",
            job_metadata={},
        )
        s.add(row)
        await s.commit()
        run_id = row.id

    metadata: dict[str, Any] = {}
    try:
        yield metadata
    except Exception as exc:
        async with session_scope() as s:
            r = await s.get(CronRun, run_id)
            assert r is not None
            r.ended_at = datetime.utcnow()
            r.status = "failed"
            r.error_message = str(exc)[:500]
            r.job_metadata = metadata
            await s.commit()
        raise
    else:
        async with session_scope() as s:
            r = await s.get(CronRun, run_id)
            assert r is not None
            r.ended_at = datetime.utcnow()
            r.status = "success"
            r.job_metadata = metadata
            await s.commit()
