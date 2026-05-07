"""Prompts CRUD + voting/copy/view tracking endpoints.

Public read endpoints (``GET /api/v1/prompts`` and the per-slug detail)
return only ``status='published'`` rows for non-authors. Authors can
fetch their own pending/rejected prompts by slug (so their dashboard
"my submissions" view works).

Spam guards:
  * Create requires ``email_verified=True``.
  * Daily 5-prompt limit per user, counted by ``created_at >= today UTC``.
  * Title and body length capped in the schema (200 / 5000 chars).
  * Vote is idempotent on ``(user_id, prompt_id)`` PK.
  * Copy-track is rate-limited per (user_or_ip, prompt_id) at 30 seconds.
"""

from datetime import datetime, timedelta
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select

from app.db import session_scope
from app.deps import current_user, require_email_verified
from app.models import Prompt, PromptCategory, PromptCopyEvent, PromptVote, User
from app.schemas.prompts import PromptCreate, PromptOut, PromptUpdate
from app.services.slug import slugify

router = APIRouter(prefix="/api/v1/prompts", tags=["prompts"])

DAILY_PROMPT_LIMIT: int = 5
COPY_TRACK_COOLDOWN_SECONDS: int = 30


def _to_out(p: Prompt, category_slug: str) -> dict[str, Any]:
    """Hand-build the response dict so we can attach ``category_slug`` (joined)."""
    return {
        "id": p.id,
        "slug": p.slug,
        "title": p.title,
        "description": p.description,
        "body": p.body,
        "category_slug": category_slug,
        "tags": p.tags,
        "variables": p.variables,
        "example_input": p.example_input,
        "example_output": p.example_output,
        "language": p.language,
        "upvotes": p.upvotes,
        "copies": p.copies,
        "views": p.views,
        "status": p.status,
        "created_at": p.created_at,
        "updated_at": p.updated_at,
    }


async def _resolve_category_id(s: Any, slug: str) -> int:
    cat = (await s.scalars(select(PromptCategory).where(PromptCategory.slug == slug))).one_or_none()
    if cat is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown category: {slug}")
    return cat.id


async def _unique_slug(s: Any, base: str) -> str:
    """Append a numeric suffix until the slug is free."""
    slug = base
    n = 2
    while (await s.scalars(select(Prompt.id).where(Prompt.slug == slug))).one_or_none() is not None:
        slug = f"{base}-{n}"
        n += 1
    return slug


# --- create / list / detail / patch / delete ----------------------------------


@router.post("", response_model=PromptOut, status_code=status.HTTP_201_CREATED)
async def create_prompt(
    payload: PromptCreate,
    user: Annotated[User, Depends(require_email_verified)],
) -> dict[str, Any]:
    async with session_scope() as s:
        # Daily 5-limit (UTC day window).
        day_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        count_today = cast(
            int,
            (
                await s.execute(
                    select(func.count())
                    .select_from(Prompt)
                    .where(
                        Prompt.author_user_id == user.id,
                        Prompt.created_at >= day_start,
                    )
                )
            ).scalar_one(),
        )
        if count_today >= DAILY_PROMPT_LIMIT:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"Daily prompt limit reached ({DAILY_PROMPT_LIMIT}/day).",
            )

        category_id = await _resolve_category_id(s, payload.category_slug)
        slug = await _unique_slug(s, slugify(payload.title))

        prompt = Prompt(
            slug=slug,
            title=payload.title,
            description=payload.description,
            body=payload.body,
            category_id=category_id,
            tags=payload.tags,
            variables=payload.variables,
            example_input=payload.example_input,
            example_output=payload.example_output,
            author_user_id=user.id,
            language=payload.language,
            status="pending",
        )
        s.add(prompt)
        await s.commit()
        await s.refresh(prompt)
        return _to_out(prompt, payload.category_slug)


@router.get("", response_model=list[PromptOut])
async def list_prompts(
    category: str | None = Query(default=None),
    lang: str | None = Query(default=None),
    q: str | None = Query(default=None),
    sort: str = Query(default="new"),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict[str, Any]]:
    async with session_scope() as s:
        stmt = (
            select(Prompt, PromptCategory.slug)
            .join(PromptCategory, PromptCategory.id == Prompt.category_id)
            .where(Prompt.status == "published")
        )
        if category:
            stmt = stmt.where(PromptCategory.slug == category)
        if lang:
            stmt = stmt.where(Prompt.language == lang)
        if q:
            needle = f"%{q.lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(Prompt.title).like(needle),
                    func.lower(Prompt.body).like(needle),
                )
            )
        if sort == "top":
            stmt = stmt.order_by(Prompt.upvotes.desc(), Prompt.id.desc())
        else:
            stmt = stmt.order_by(Prompt.created_at.desc())
        stmt = stmt.limit(limit)
        rows = (await s.execute(stmt)).all()
        return [_to_out(p, cat_slug) for p, cat_slug in rows]


@router.get("/{slug}", response_model=PromptOut)
async def get_prompt(slug: str, request: Request) -> dict[str, Any]:
    async with session_scope() as s:
        row = (
            await s.execute(
                select(Prompt, PromptCategory.slug)
                .join(PromptCategory, PromptCategory.id == Prompt.category_id)
                .where(Prompt.slug == slug)
            )
        ).one_or_none()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND)
        prompt, cat_slug = row

        # Author can see their own pending/rejected; everyone else only sees published.
        if prompt.status != "published":
            try:
                viewer = await current_user(request.cookies.get("session"))
            except HTTPException:
                viewer = None
            if viewer is None or viewer.id != prompt.author_user_id:
                raise HTTPException(status.HTTP_404_NOT_FOUND)

        prompt.views += 1
        await s.commit()
        await s.refresh(prompt)
        return _to_out(prompt, cat_slug)


@router.patch("/{prompt_id}", response_model=PromptOut)
async def update_prompt(
    prompt_id: int,
    payload: PromptUpdate,
    user: Annotated[User, Depends(require_email_verified)],
) -> dict[str, Any]:
    async with session_scope() as s:
        prompt = (
            await s.scalars(
                select(Prompt).where(
                    Prompt.id == prompt_id,
                    Prompt.author_user_id == user.id,
                )
            )
        ).one_or_none()
        if prompt is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND)

        data = payload.model_dump(exclude_unset=True)
        if "category_slug" in data:
            prompt.category_id = await _resolve_category_id(s, data.pop("category_slug"))
        for field, value in data.items():
            setattr(prompt, field, value)
        # Edits go back through review.
        prompt.status = "pending"
        await s.commit()
        await s.refresh(prompt)

        cat_slug = (
            await s.scalars(
                select(PromptCategory.slug).where(PromptCategory.id == prompt.category_id)
            )
        ).one()
        return _to_out(prompt, cat_slug)


@router.delete("/{prompt_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_prompt(
    prompt_id: int,
    user: Annotated[User, Depends(require_email_verified)],
) -> None:
    async with session_scope() as s:
        prompt = (
            await s.scalars(
                select(Prompt).where(
                    Prompt.id == prompt_id,
                    Prompt.author_user_id == user.id,
                )
            )
        ).one_or_none()
        if prompt is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND)
        prompt.status = "deleted"
        await s.commit()


# --- vote / copy ----------------------------------------------------------


@router.post("/{prompt_id}/vote", response_model=PromptOut)
async def vote_prompt(
    prompt_id: int,
    user: Annotated[User, Depends(current_user)],
) -> dict[str, Any]:
    async with session_scope() as s:
        prompt = await s.get(Prompt, prompt_id)
        if prompt is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND)

        # Idempotent: PK is (user_id, prompt_id) — no double-count.
        existing = await s.get(PromptVote, (user.id, prompt_id))
        if existing is None:
            s.add(PromptVote(user_id=user.id, prompt_id=prompt_id))
            prompt.upvotes += 1
            await s.commit()
            await s.refresh(prompt)

        cat_slug = (
            await s.scalars(
                select(PromptCategory.slug).where(PromptCategory.id == prompt.category_id)
            )
        ).one()
        return _to_out(prompt, cat_slug)


@router.post("/{prompt_id}/copy", response_model=PromptOut)
async def copy_prompt(
    prompt_id: int,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> dict[str, Any]:
    async with session_scope() as s:
        prompt = await s.get(Prompt, prompt_id)
        if prompt is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND)

        # 30s anti-spam per (user, prompt). For anonymous users, use IP.
        actor = (
            f"u:{user.id}" if user else f"ip:{request.client.host if request.client else 'unknown'}"
        )
        cooldown_cutoff = datetime.utcnow() - timedelta(seconds=COPY_TRACK_COOLDOWN_SECONDS)
        recent = (
            await s.scalars(
                select(PromptCopyEvent).where(
                    PromptCopyEvent.prompt_id == prompt_id,
                    PromptCopyEvent.user_or_ip == actor,
                    PromptCopyEvent.created_at >= cooldown_cutoff,
                )
            )
        ).first()
        if recent is None:
            s.add(PromptCopyEvent(prompt_id=prompt_id, user_or_ip=actor))
            prompt.copies += 1
            await s.commit()
            await s.refresh(prompt)

        cat_slug = (
            await s.scalars(
                select(PromptCategory.slug).where(PromptCategory.id == prompt.category_id)
            )
        ).one()
        return _to_out(prompt, cat_slug)
