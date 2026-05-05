"""Digest filter pipeline.

Given a :class:`~app.models.Task`, produces a ranked, deduplicated list
of recent :class:`~app.models.Paper` rows for inclusion in today's
digest. Stages, in order:

1. **Category + recency**: papers whose ``primary_category`` is in
   ``task.arxiv_categories`` and whose ``published_at`` is within the
   last ``since_hours`` (default 36, to absorb timezone slop).
2. **Keyword filter**: if ``task.keywords`` is non-empty, retain papers
   where at least ``task.min_keyword_match`` keywords appear in the
   concatenated title+abstract (case-insensitive substring match).
3. **Semantic rerank**: if ``task.interest_description`` is set, sort
   candidates by descending ``cosine(task_vec, paper_vec)`` where both
   vectors are 1536-d unit-length BLOBs from sqlite-vec. Papers without
   a stored vector get score 0 (sink to the bottom).
4. **Delivery dedup**: drop any paper already delivered to this task
   via the ``email`` channel (RSS deliveries don't count — the feed is
   pull-based and re-appearances are fine).
5. **Cap**: top ``task.max_papers_per_day``.

The task embedding is cached in ``task_embeddings`` keyed by ``task_id``
and invalidated when ``source_text != task.interest_description``.
"""

from collections.abc import Sequence
from datetime import datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Delivery, Paper, Task, TaskEmbedding
from app.services.embedding import embed_text, from_blob, to_blob


async def candidates_for_task(
    s: AsyncSession,
    task: Task,
    *,
    since_hours: int = 36,
) -> list[Paper]:
    cutoff = datetime.utcnow() - timedelta(hours=since_hours)
    rows = await s.execute(
        select(Paper).where(
            Paper.primary_category.in_(task.arxiv_categories),
            Paper.published_at >= cutoff,
        )
    )
    return list(rows.scalars())


def keyword_match(paper: Paper, task: Task) -> int:
    if not task.keywords:
        return 0
    haystack = (paper.title + " " + paper.abstract).lower()
    return sum(1 for k in task.keywords if k.lower() in haystack)


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Dot product. Equals cosine similarity when both inputs are unit-length.

    MockBackend and OpenAI's text-embedding-3-small both return L2-normalized
    vectors, so this is the right metric for our pipeline.
    """
    return sum(x * y for x, y in zip(a, b, strict=True))


async def get_or_compute_task_embedding(
    s: AsyncSession,
    task: Task,
) -> list[float] | None:
    if not task.interest_description:
        return None
    existing = await s.get(TaskEmbedding, task.id)
    if existing and existing.source_text == task.interest_description:
        return from_blob(existing.embedding)

    vec = await embed_text(task.interest_description)
    blob = to_blob(vec)
    if existing:
        existing.embedding = blob
        existing.source_text = task.interest_description
    else:
        s.add(
            TaskEmbedding(
                task_id=task.id,
                embedding=blob,
                source_text=task.interest_description,
            )
        )
    await s.commit()
    # Round-trip through the blob so the freshly-computed and cached returns
    # are bit-identical (float32 precision either way) — callers can compare
    # vectors across calls without tripping on float64-vs-float32 noise.
    return from_blob(blob)


async def get_paper_embedding(s: AsyncSession, paper_id: str) -> list[float] | None:
    row = await s.execute(
        text("SELECT embedding FROM paper_vectors WHERE paper_id = :p"),
        {"p": paper_id},
    )
    r = row.first()
    if r is None:
        return None
    return from_blob(r[0])


async def select_papers_for_task(s: AsyncSession, task: Task) -> list[Paper]:
    cands = await candidates_for_task(s, task)

    if task.keywords:
        cands = [p for p in cands if keyword_match(p, task) >= task.min_keyword_match]

    task_vec = await get_or_compute_task_embedding(s, task)
    if task_vec is not None:
        scored: list[tuple[float, Paper]] = []
        for p in cands:
            pv = await get_paper_embedding(s, p.id)
            score = cosine(task_vec, pv) if pv is not None else 0.0
            scored.append((score, p))
        scored.sort(key=lambda x: -x[0])
        cands = [p for _, p in scored]

    delivered_ids: set[str] = set(
        (
            await s.scalars(
                select(Delivery.paper_id).where(
                    Delivery.task_id == task.id,
                    Delivery.channel == "email",
                )
            )
        ).all()
    )
    cands = [p for p in cands if p.id not in delivered_ids]

    return cands[: task.max_papers_per_day]
