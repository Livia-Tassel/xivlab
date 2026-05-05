"""Per-task Atom feed endpoint.

Auth is the ``rss_token`` query parameter — feed readers can't carry
session cookies. The token is opaque and uniquely indexed on
``tasks.rss_token``; we still match it against the task fetched by
``(user_id, task_id)`` to keep all three pieces consistent and avoid
disclosing task existence on bad tokens.

The feed pulls papers via the ``Delivery`` table (channel doesn't
matter — anything that's been delivered to the task is fair game in
the feed) within a 30-day window, capped at 50 entries.
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import select

from app.config import get_settings
from app.db import session_scope
from app.models import Delivery, Paper, Task
from app.services.feed_renderer import render_atom

router = APIRouter()

_FEED_WINDOW_DAYS = 30
_FEED_MAX_ENTRIES = 50


@router.get("/rss/{user_id}/{task_id}/feed.xml")
async def task_feed(user_id: int, task_id: int, token: str = Query(default="")) -> Response:
    async with session_scope() as s:
        task = (
            await s.scalars(select(Task).where(Task.id == task_id, Task.user_id == user_id))
        ).one_or_none()
        if task is None or task.rss_token != token:
            raise HTTPException(status.HTTP_404_NOT_FOUND)

        cutoff = datetime.utcnow() - timedelta(days=_FEED_WINDOW_DAYS)
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
                    .limit(_FEED_MAX_ENTRIES)
                )
            ).all()
        )

    xml = render_atom(
        task,
        papers,
        base_url=get_settings().app_base_url,
        user_id=user_id,
    )
    return Response(content=xml, media_type="application/atom+xml")
