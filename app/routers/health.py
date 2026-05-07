"""Liveness + last-cron-run health endpoint."""

from typing import Any

from fastapi import APIRouter
from sqlalchemy import select, text

from app.db import session_scope
from app.models import CronRun

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, Any]:
    async with session_scope() as s:
        await s.execute(text("SELECT 1"))
        last_arxiv = (
            await s.execute(
                select(CronRun)
                .where(CronRun.job_name == "fetch_arxiv")
                .order_by(CronRun.started_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
    return {
        "status": "ok",
        "db": "ok",
        "last_arxiv_run": last_arxiv.started_at.isoformat() if last_arxiv else None,
    }
