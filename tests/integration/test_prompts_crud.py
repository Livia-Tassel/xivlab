"""Integration tests for the Prompts CRUD API + spam guards.

Endpoints under test (mounted at ``/api/v1/prompts``):
  - POST                 — create a prompt; requires verified email; daily 5-limit
  - GET                  — public list with filters (category/sort/lang/q); excludes pending/rejected
  - GET   /{slug}        — public detail; bumps view count; excludes pending/rejected for non-author
  - PATCH /{prompt_id}   — author-only edit (resets status to 'pending')
  - DELETE /{prompt_id}  — author-only soft-removal via status='deleted'
  - POST  /{prompt_id}/vote   — idempotent upvote
  - POST  /{prompt_id}/copy   — copy-track event with 30s anti-spam per (user_or_ip, prompt)

Categories are pre-seeded by conftest's autouse ``_reset_db`` fixture
(9 categories incl. "paper-writing"), so tests can reference them by slug.
"""

from datetime import datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select

from app.db import session_scope
from app.models import Prompt, PromptCopyEvent, PromptVote, User


async def _make_verified_user(client: AsyncClient, email: str = "pu@x.dev") -> int:
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "passw0rd!"},
    )
    async with session_scope() as s:
        u = (await s.scalars(select(User).where(User.email == email))).one()
        u.email_verified = True
        await s.commit()
        user_id = u.id
    await client.post("/api/v1/auth/login", json={"email": email, "password": "passw0rd!"})
    return user_id


def _payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "title": "Polish my paper",
        "description": "Polish-EN academic prose",
        "body": "You are an academic editor. Polish:\n\n{{text}}",
        "category_slug": "paper-writing",
        "tags": ["editing", "english"],
        "language": "zh",
    }
    base.update(overrides)
    return base


# --- create ---------------------------------------------------------------


async def test_create_prompt_requires_login(client: AsyncClient) -> None:
    r = await client.post("/api/v1/prompts", json=_payload())
    assert r.status_code == 401


async def test_create_prompt_requires_verified_email(
    client: AsyncClient,
) -> None:
    """Unverified user gets 403, not 401."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": "x@y.dev", "password": "passw0rd!"},
    )
    await client.post("/api/v1/auth/login", json={"email": "x@y.dev", "password": "passw0rd!"})
    r = await client.post("/api/v1/prompts", json=_payload())
    assert r.status_code == 403


async def test_create_prompt_201_returns_payload_with_slug_and_pending_status(
    client: AsyncClient,
) -> None:
    await _make_verified_user(client)
    r = await client.post("/api/v1/prompts", json=_payload(title="Hello World"))
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["title"] == "Hello World"
    assert data["slug"] == "hello-world"
    assert data["status"] == "pending"
    assert data["category_slug"] == "paper-writing"
    assert data["upvotes"] == 0
    assert data["copies"] == 0
    assert data["views"] == 0
    assert "id" in data


async def test_create_prompt_unknown_category_400(client: AsyncClient) -> None:
    await _make_verified_user(client)
    r = await client.post("/api/v1/prompts", json=_payload(category_slug="not-a-real-category"))
    assert r.status_code == 400


async def test_create_prompt_title_too_long_422(client: AsyncClient) -> None:
    await _make_verified_user(client)
    r = await client.post("/api/v1/prompts", json=_payload(title="x" * 201))
    assert r.status_code == 422


async def test_create_prompt_body_too_long_422(client: AsyncClient) -> None:
    await _make_verified_user(client)
    r = await client.post("/api/v1/prompts", json=_payload(body="x" * 5001))
    assert r.status_code == 422


async def test_create_prompt_daily_limit_5(client: AsyncClient) -> None:
    """6th submission today returns 429."""
    await _make_verified_user(client)
    for i in range(5):
        r = await client.post("/api/v1/prompts", json=_payload(title=f"P{i}"))
        assert r.status_code == 201, f"i={i} {r.text}"
    r6 = await client.post("/api/v1/prompts", json=_payload(title="P5"))
    assert r6.status_code == 429


async def test_create_prompt_dedupes_slug_collision(client: AsyncClient) -> None:
    """Two prompts with the same title get distinct slugs."""
    await _make_verified_user(client)
    a = await client.post("/api/v1/prompts", json=_payload(title="Same Name"))
    b = await client.post("/api/v1/prompts", json=_payload(title="Same Name"))
    assert a.status_code == 201
    assert b.status_code == 201
    assert a.json()["slug"] != b.json()["slug"]


# --- list -----------------------------------------------------------------


async def _seed_published_prompt(
    user_id: int,
    *,
    title: str = "Published",
    category_slug: str = "paper-writing",
    language: str = "zh",
    upvotes: int = 0,
    status: str = "published",
) -> int:
    from app.models import PromptCategory
    from app.services.slug import slugify

    async with session_scope() as s:
        cat = (
            await s.scalars(select(PromptCategory).where(PromptCategory.slug == category_slug))
        ).one()
        p = Prompt(
            slug=slugify(title) + f"-{user_id}-{title}"[:8],
            title=title,
            description=None,
            body="body",
            category_id=cat.id,
            tags=[],
            author_user_id=user_id,
            language=language,
            upvotes=upvotes,
            status=status,
        )
        s.add(p)
        await s.commit()
        await s.refresh(p)
        return p.id


async def test_list_returns_only_published(client: AsyncClient) -> None:
    user_id = await _make_verified_user(client)
    await _seed_published_prompt(user_id, title="P1", status="published")
    await _seed_published_prompt(user_id, title="P2", status="pending")
    await _seed_published_prompt(user_id, title="P3", status="rejected")

    r = await client.get("/api/v1/prompts")
    assert r.status_code == 200
    titles = {p["title"] for p in r.json()}
    assert titles == {"P1"}


async def test_list_filters_by_category(client: AsyncClient) -> None:
    user_id = await _make_verified_user(client)
    await _seed_published_prompt(user_id, title="A", category_slug="paper-writing")
    await _seed_published_prompt(user_id, title="B", category_slug="code")

    r = await client.get("/api/v1/prompts", params={"category": "code"})
    titles = {p["title"] for p in r.json()}
    assert titles == {"B"}


async def test_list_filters_by_language(client: AsyncClient) -> None:
    user_id = await _make_verified_user(client)
    await _seed_published_prompt(user_id, title="ZH", language="zh")
    await _seed_published_prompt(user_id, title="EN", language="en")

    r = await client.get("/api/v1/prompts", params={"lang": "en"})
    titles = {p["title"] for p in r.json()}
    assert titles == {"EN"}


async def test_list_filters_by_query_string(client: AsyncClient) -> None:
    user_id = await _make_verified_user(client)
    await _seed_published_prompt(user_id, title="LLM Agent Survey")
    await _seed_published_prompt(user_id, title="Diffusion Models")

    r = await client.get("/api/v1/prompts", params={"q": "agent"})
    titles = {p["title"] for p in r.json()}
    assert titles == {"LLM Agent Survey"}


async def test_list_sorts_by_upvotes_desc(client: AsyncClient) -> None:
    user_id = await _make_verified_user(client)
    await _seed_published_prompt(user_id, title="Low", upvotes=1)
    await _seed_published_prompt(user_id, title="High", upvotes=10)
    await _seed_published_prompt(user_id, title="Mid", upvotes=5)

    r = await client.get("/api/v1/prompts", params={"sort": "top"})
    titles = [p["title"] for p in r.json()]
    assert titles == ["High", "Mid", "Low"]


# --- detail / view-track --------------------------------------------------


async def test_get_prompt_increments_views(client: AsyncClient) -> None:
    user_id = await _make_verified_user(client)
    pid = await _seed_published_prompt(user_id, title="Detail")
    async with session_scope() as s:
        slug = (await s.get(Prompt, pid)).slug

    r1 = await client.get(f"/api/v1/prompts/{slug}")
    assert r1.status_code == 200
    assert r1.json()["views"] == 1

    r2 = await client.get(f"/api/v1/prompts/{slug}")
    assert r2.json()["views"] == 2


async def test_get_pending_prompt_404_for_non_author(
    client: AsyncClient,
) -> None:
    author_id = await _make_verified_user(client, email="author@x.dev")
    pid = await _seed_published_prompt(author_id, title="Pending", status="pending")
    async with session_scope() as s:
        slug = (await s.get(Prompt, pid)).slug

    # Log out and log in as someone else
    other_client = client
    await other_client.post("/api/v1/auth/logout")
    await _make_verified_user(other_client, email="other@x.dev")

    r = await other_client.get(f"/api/v1/prompts/{slug}")
    assert r.status_code == 404


# --- patch / delete -------------------------------------------------------


async def test_patch_prompt_only_by_author(client: AsyncClient) -> None:
    author_id = await _make_verified_user(client, email="author@x.dev")
    pid = await _seed_published_prompt(author_id, title="Mine")

    # Author can patch.
    r_self = await client.patch(
        f"/api/v1/prompts/{pid}",
        json={"title": "Mine updated"},
    )
    assert r_self.status_code == 200, r_self.text
    assert r_self.json()["title"] == "Mine updated"
    # Editing resets to pending so admin re-reviews.
    assert r_self.json()["status"] == "pending"

    # Different user cannot.
    await client.post("/api/v1/auth/logout")
    await _make_verified_user(client, email="stranger@x.dev")
    r_other = await client.patch(
        f"/api/v1/prompts/{pid}",
        json={"title": "Hijacked"},
    )
    assert r_other.status_code == 404


async def test_delete_prompt_only_by_author(client: AsyncClient) -> None:
    author_id = await _make_verified_user(client, email="author@x.dev")
    pid = await _seed_published_prompt(author_id, title="DeleteMe")

    r = await client.delete(f"/api/v1/prompts/{pid}")
    assert r.status_code == 204

    async with session_scope() as s:
        p = await s.get(Prompt, pid)
        assert p is not None
        assert p.status == "deleted"


# --- vote -----------------------------------------------------------------


async def test_vote_idempotent(client: AsyncClient) -> None:
    user_id = await _make_verified_user(client)
    pid = await _seed_published_prompt(user_id, title="Voted")

    r1 = await client.post(f"/api/v1/prompts/{pid}/vote")
    assert r1.status_code == 200
    assert r1.json()["upvotes"] == 1

    r2 = await client.post(f"/api/v1/prompts/{pid}/vote")
    assert r2.status_code == 200
    assert r2.json()["upvotes"] == 1  # still 1 — idempotent

    async with session_scope() as s:
        votes = (await s.scalars(select(PromptVote))).all()
        assert len(votes) == 1


async def test_vote_requires_login(client: AsyncClient) -> None:
    user_id_setup_client = await _make_verified_user(client, email="setup@x.dev")
    pid = await _seed_published_prompt(user_id_setup_client, title="V")
    await client.post("/api/v1/auth/logout")

    r = await client.post(f"/api/v1/prompts/{pid}/vote")
    assert r.status_code == 401


# --- copy-track -----------------------------------------------------------


async def test_copy_track_creates_event_first_time(client: AsyncClient) -> None:
    user_id = await _make_verified_user(client)
    pid = await _seed_published_prompt(user_id, title="C")

    r = await client.post(f"/api/v1/prompts/{pid}/copy")
    assert r.status_code == 200
    assert r.json()["copies"] == 1

    async with session_scope() as s:
        events = (await s.scalars(select(PromptCopyEvent))).all()
        assert len(events) == 1


async def test_copy_track_30s_anti_spam(client: AsyncClient) -> None:
    """Same user copying same prompt within 30s does not double-count."""
    user_id = await _make_verified_user(client)
    pid = await _seed_published_prompt(user_id, title="CC")

    r1 = await client.post(f"/api/v1/prompts/{pid}/copy")
    assert r1.status_code == 200
    assert r1.json()["copies"] == 1

    # Second copy within 30s — no new event, copies stays at 1.
    r2 = await client.post(f"/api/v1/prompts/{pid}/copy")
    assert r2.status_code == 200
    assert r2.json()["copies"] == 1

    async with session_scope() as s:
        events = (await s.scalars(select(PromptCopyEvent))).all()
        assert len(events) == 1


async def test_copy_track_after_30s_counts_again(client: AsyncClient) -> None:
    user_id = await _make_verified_user(client)
    pid = await _seed_published_prompt(user_id, title="CCC")

    # Manually backdate the first event.
    r1 = await client.post(f"/api/v1/prompts/{pid}/copy")
    assert r1.status_code == 200

    async with session_scope() as s:
        ev = (await s.scalars(select(PromptCopyEvent))).one()
        ev.created_at = datetime.utcnow() - timedelta(seconds=31)
        await s.commit()

    r2 = await client.post(f"/api/v1/prompts/{pid}/copy")
    assert r2.json()["copies"] == 2
    async with session_scope() as s:
        assert len((await s.scalars(select(PromptCopyEvent))).all()) == 2
