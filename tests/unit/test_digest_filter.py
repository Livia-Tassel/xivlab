"""Tests for the digest filter pipeline.

Pure-function helpers (``keyword_match``, ``cosine``) live in the first
section. DB-backed pipeline tests follow; they rely on the autouse
``_reset_db`` fixture from ``tests/conftest.py`` for a clean schema +
the ``paper_vectors`` virtual table.

The semantic-rerank test seeds ``paper_vectors`` and ``task_embeddings``
with hand-crafted unit vectors so the expected ordering is exact and
independent of MockBackend's hash-derived noise.
"""

from datetime import datetime, timedelta

from sqlalchemy import select, text

from app.db import session_scope
from app.models import Delivery, Paper, Task, TaskEmbedding, User
from app.services.digest import (
    cosine,
    get_or_compute_task_embedding,
    keyword_match,
    select_papers_for_task,
)
from app.services.embedding import EMBEDDING_DIM, to_blob

# --- fixtures -------------------------------------------------------------


def _make_task(
    user_id: int,
    *,
    name: str = "T",
    arxiv_categories: list[str] | None = None,
    keywords: list[str] | None = None,
    min_keyword_match: int = 1,
    interest_description: str | None = None,
    max_papers_per_day: int = 10,
    rss_token: str = "rss-token-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
) -> Task:
    return Task(
        user_id=user_id,
        name=name,
        arxiv_categories=arxiv_categories or ["cs.AI"],
        keywords=keywords,
        min_keyword_match=min_keyword_match,
        interest_description=interest_description,
        max_papers_per_day=max_papers_per_day,
        delivery_time="08:00",
        delivery_channels=["email"],
        rss_token=rss_token,
        enabled=True,
    )


def _make_paper(
    pid: str,
    *,
    title: str = "T",
    abstract: str = "A",
    primary_category: str = "cs.AI",
    all_categories: list[str] | None = None,
    published_at: datetime | None = None,
) -> Paper:
    return Paper(
        id=pid,
        title=title,
        abstract=abstract,
        authors=["X"],
        primary_category=primary_category,
        all_categories=all_categories or [primary_category],
        published_at=published_at or datetime.utcnow(),
        pdf_url=None,
    )


async def _make_user(email: str = "user@x.dev") -> int:
    async with session_scope() as s:
        u = User(email=email, password_hash="x", email_verified=True)
        s.add(u)
        await s.commit()
        return u.id


def _unit_vec(idx: int) -> list[float]:
    """Return the ``idx``-th standard basis vector in 1536-d (length 1.0)."""
    v = [0.0] * EMBEDDING_DIM
    v[idx] = 1.0
    return v


# --- pure-function tests --------------------------------------------------


def test_keyword_match_counts_matches_case_insensitively() -> None:
    user_id = 1
    task = _make_task(user_id, keywords=["RAG", "retrieval"])
    paper = _make_paper("p", title="rag-augmented LLMs", abstract="RETRIEVAL pipelines")
    assert keyword_match(paper, task) == 2


def test_keyword_match_zero_when_no_keywords() -> None:
    task = _make_task(1, keywords=None)
    paper = _make_paper("p", title="anything", abstract="anything")
    assert keyword_match(paper, task) == 0


def test_keyword_match_searches_title_and_abstract() -> None:
    task = _make_task(1, keywords=["foo"])
    p_title_only = _make_paper("p1", title="foo paper", abstract="zzz")
    p_abstract_only = _make_paper("p2", title="zzz", abstract="A foo discussion")
    p_neither = _make_paper("p3", title="zzz", abstract="zzz")
    assert keyword_match(p_title_only, task) == 1
    assert keyword_match(p_abstract_only, task) == 1
    assert keyword_match(p_neither, task) == 0


def test_cosine_dot_product_of_orthogonal_unit_vectors_is_zero() -> None:
    a = _unit_vec(0)
    b = _unit_vec(1)
    assert cosine(a, b) == 0.0


def test_cosine_of_identical_unit_vector_is_one() -> None:
    a = _unit_vec(7)
    assert cosine(a, a) == 1.0


# --- DB-backed pipeline tests ---------------------------------------------


async def test_select_filters_by_primary_category() -> None:
    user_id = await _make_user()
    async with session_scope() as s:
        task = _make_task(user_id, arxiv_categories=["cs.AI"])
        s.add(task)
        s.add(_make_paper("p-ai", primary_category="cs.AI"))
        s.add(_make_paper("p-lg", primary_category="cs.LG"))
        await s.commit()

        result = await select_papers_for_task(s, task)
    ids = {p.id for p in result}
    assert ids == {"p-ai"}


async def test_select_filters_out_papers_outside_recency_window() -> None:
    user_id = await _make_user()
    now = datetime.utcnow()
    async with session_scope() as s:
        task = _make_task(user_id)
        s.add(task)
        s.add(_make_paper("p-fresh", published_at=now - timedelta(hours=2)))
        s.add(_make_paper("p-stale", published_at=now - timedelta(days=5)))
        await s.commit()

        result = await select_papers_for_task(s, task)
    ids = {p.id for p in result}
    assert ids == {"p-fresh"}


async def test_select_keyword_filter_respects_min_match() -> None:
    user_id = await _make_user()
    async with session_scope() as s:
        task = _make_task(
            user_id,
            keywords=["LLM", "agent"],
            min_keyword_match=2,
        )
        s.add(task)
        s.add(_make_paper("p-both", title="LLM agent survey", abstract="..."))
        s.add(_make_paper("p-one", title="LLM survey", abstract="no a-word here"))
        s.add(_make_paper("p-none", title="diffusion models", abstract="image"))
        await s.commit()

        result = await select_papers_for_task(s, task)
    ids = {p.id for p in result}
    assert ids == {"p-both"}


async def test_select_semantic_rerank_orders_by_similarity() -> None:
    """Paper whose stored vector matches the task vector ranks above an orthogonal one."""
    user_id = await _make_user()
    async with session_scope() as s:
        task = _make_task(
            user_id,
            interest_description="anything — embedding is pre-seeded below",
            max_papers_per_day=10,
        )
        s.add(task)
        s.add(_make_paper("p-match", title="m", abstract="m"))
        s.add(_make_paper("p-orthog", title="o", abstract="o"))
        await s.commit()
        await s.refresh(task)

        match_vec = _unit_vec(0)
        orthog_vec = _unit_vec(1)
        # Pre-seed the task embedding so get_or_compute_task_embedding returns it
        # directly without calling the (deterministic but noisy) MockBackend.
        s.add(
            TaskEmbedding(
                task_id=task.id,
                embedding=to_blob(match_vec),
                source_text=task.interest_description or "",
            )
        )
        await s.execute(
            text("INSERT INTO paper_vectors(paper_id, embedding) VALUES (:pid, :emb)"),
            {"pid": "p-match", "emb": to_blob(match_vec)},
        )
        await s.execute(
            text("INSERT INTO paper_vectors(paper_id, embedding) VALUES (:pid, :emb)"),
            {"pid": "p-orthog", "emb": to_blob(orthog_vec)},
        )
        await s.commit()

        result = await select_papers_for_task(s, task)
    assert [p.id for p in result] == ["p-match", "p-orthog"]


async def test_select_excludes_already_delivered_via_email() -> None:
    user_id = await _make_user()
    async with session_scope() as s:
        task = _make_task(user_id)
        s.add(task)
        s.add(_make_paper("p-new"))
        s.add(_make_paper("p-delivered"))
        await s.commit()
        await s.refresh(task)

        s.add(
            Delivery(
                user_id=user_id,
                task_id=task.id,
                paper_id="p-delivered",
                channel="email",
            )
        )
        await s.commit()

        result = await select_papers_for_task(s, task)
    ids = {p.id for p in result}
    assert ids == {"p-new"}


async def test_select_does_not_dedupe_rss_only_deliveries() -> None:
    """A paper delivered via RSS only should still appear in the email digest."""
    user_id = await _make_user()
    async with session_scope() as s:
        task = _make_task(user_id)
        s.add(task)
        s.add(_make_paper("p-rss-only"))
        await s.commit()
        await s.refresh(task)

        s.add(
            Delivery(
                user_id=user_id,
                task_id=task.id,
                paper_id="p-rss-only",
                channel="rss",
            )
        )
        await s.commit()

        result = await select_papers_for_task(s, task)
    assert {p.id for p in result} == {"p-rss-only"}


async def test_select_caps_at_max_papers_per_day() -> None:
    user_id = await _make_user()
    async with session_scope() as s:
        task = _make_task(user_id, max_papers_per_day=5)
        s.add(task)
        for i in range(20):
            s.add(_make_paper(f"p{i:02d}"))
        await s.commit()

        result = await select_papers_for_task(s, task)
    assert len(result) == 5


async def test_get_or_compute_task_embedding_caches() -> None:
    user_id = await _make_user()
    async with session_scope() as s:
        task = _make_task(user_id, interest_description="LLM agents and tool use")
        s.add(task)
        await s.commit()
        await s.refresh(task)

        v1 = await get_or_compute_task_embedding(s, task)
        cached = await s.get(TaskEmbedding, task.id)
        assert cached is not None
        assert cached.source_text == "LLM agents and tool use"

        v2 = await get_or_compute_task_embedding(s, task)
    assert v1 == v2
    assert v1 is not None
    assert len(v1) == EMBEDDING_DIM


async def test_get_or_compute_task_embedding_invalidates_on_text_change() -> None:
    user_id = await _make_user()
    async with session_scope() as s:
        task = _make_task(user_id, interest_description="topic A")
        s.add(task)
        await s.commit()
        await s.refresh(task)

        v_a = await get_or_compute_task_embedding(s, task)
        task.interest_description = "topic B — completely different"
        await s.commit()
        v_b = await get_or_compute_task_embedding(s, task)

        cached = await s.get(TaskEmbedding, task.id)
        assert cached is not None
        assert cached.source_text == "topic B — completely different"
    assert v_a != v_b


async def test_get_or_compute_task_embedding_returns_none_when_no_description() -> None:
    user_id = await _make_user()
    async with session_scope() as s:
        task = _make_task(user_id, interest_description=None)
        s.add(task)
        await s.commit()
        await s.refresh(task)

        v = await get_or_compute_task_embedding(s, task)
        cached = (await s.execute(select(TaskEmbedding))).scalars().all()
    assert v is None
    assert cached == []
