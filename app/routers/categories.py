"""Public categories list endpoint.

Returns all prompt categories sorted by ``sort_order`` for the home and
nav menus. No auth required — categories are static taxonomy.
"""

from typing import Any

from fastapi import APIRouter
from sqlalchemy import select

from app.db import session_scope
from app.models import PromptCategory

router = APIRouter(prefix="/api/v1/categories", tags=["categories"])


@router.get("", response_model=list[dict[str, Any]])
async def list_categories() -> list[dict[str, Any]]:
    async with session_scope() as s:
        rows = (
            (await s.execute(select(PromptCategory).order_by(PromptCategory.sort_order)))
            .scalars()
            .all()
        )
        return [
            {
                "slug": c.slug,
                "name": c.name,
                "description": c.description,
                "icon": c.icon,
            }
            for c in rows
        ]
