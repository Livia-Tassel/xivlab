"""Admin endpoints for the prompt review queue.

Admin = ``User.is_admin = True``. The dependency is reused from ``app.deps``.
All endpoints under ``/api/v1/admin/*`` return 403 for non-admins (and 401
for unauthenticated callers — handled by ``current_user`` upstream).
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.db import session_scope
from app.deps import require_admin
from app.models import Prompt, PromptCategory, User

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


class RejectPayload(BaseModel):
    review_note: str | None = Field(default=None, max_length=2000)


def _to_admin_out(p: Prompt, category_slug: str, author_email: str) -> dict[str, Any]:
    return {
        "id": p.id,
        "slug": p.slug,
        "title": p.title,
        "description": p.description,
        "body": p.body,
        "category_slug": category_slug,
        "language": p.language,
        "status": p.status,
        "review_note": p.review_note,
        "author_email": author_email,
        "created_at": p.created_at,
    }


@router.get("/pending-prompts")
async def list_pending_prompts(
    _: Annotated[User, Depends(require_admin)],
) -> list[dict[str, Any]]:
    async with session_scope() as s:
        rows = (
            await s.execute(
                select(Prompt, PromptCategory.slug, User.email)
                .join(PromptCategory, PromptCategory.id == Prompt.category_id)
                .join(User, User.id == Prompt.author_user_id)
                .where(Prompt.status == "pending")
                .order_by(Prompt.created_at.asc())
            )
        ).all()
        return [_to_admin_out(p, cs, em) for p, cs, em in rows]


@router.post("/prompts/{prompt_id}/approve")
async def approve_prompt(
    prompt_id: int,
    _: Annotated[User, Depends(require_admin)],
) -> dict[str, Any]:
    async with session_scope() as s:
        prompt = await s.get(Prompt, prompt_id)
        if prompt is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND)
        prompt.status = "published"
        prompt.review_note = None
        await s.commit()
        await s.refresh(prompt)
        cat_slug = (
            await s.scalars(
                select(PromptCategory.slug).where(PromptCategory.id == prompt.category_id)
            )
        ).one()
        author_email = (
            await s.scalars(select(User.email).where(User.id == prompt.author_user_id))
        ).one()
        return _to_admin_out(prompt, cat_slug, author_email)


@router.post("/prompts/{prompt_id}/reject")
async def reject_prompt(
    prompt_id: int,
    payload: RejectPayload,
    _: Annotated[User, Depends(require_admin)],
) -> dict[str, Any]:
    async with session_scope() as s:
        prompt = await s.get(Prompt, prompt_id)
        if prompt is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND)
        prompt.status = "rejected"
        prompt.review_note = payload.review_note
        await s.commit()
        await s.refresh(prompt)
        cat_slug = (
            await s.scalars(
                select(PromptCategory.slug).where(PromptCategory.id == prompt.category_id)
            )
        ).one()
        author_email = (
            await s.scalars(select(User.email).where(User.id == prompt.author_user_id))
        ).one()
        return _to_admin_out(prompt, cat_slug, author_email)
