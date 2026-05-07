"""Admin queue + approve/reject endpoints."""

from httpx import AsyncClient
from sqlalchemy import select

from app.db import session_scope
from app.models import Prompt, PromptCategory, User
from app.services.password import hash_password


async def _make_admin(client: AsyncClient, email: str = "admin@x.dev") -> int:
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "passw0rd!"},
    )
    async with session_scope() as s:
        u = (await s.scalars(select(User).where(User.email == email))).one()
        u.email_verified = True
        u.is_admin = True
        await s.commit()
        uid = u.id
    await client.post("/api/v1/auth/login", json={"email": email, "password": "passw0rd!"})
    return uid


async def _make_regular(client: AsyncClient, email: str = "user@x.dev") -> int:
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "passw0rd!"},
    )
    async with session_scope() as s:
        u = (await s.scalars(select(User).where(User.email == email))).one()
        u.email_verified = True
        await s.commit()
        uid = u.id
    await client.post("/api/v1/auth/login", json={"email": email, "password": "passw0rd!"})
    return uid


async def _seed_pending(author_id: int, title: str = "Pending One") -> int:
    async with session_scope() as s:
        cat = (await s.scalars(select(PromptCategory).where(PromptCategory.slug == "code"))).one()
        p = Prompt(
            slug=f"pending-{title.lower().replace(' ', '-')}",
            title=title,
            body="body",
            category_id=cat.id,
            tags=[],
            author_user_id=author_id,
            language="zh",
            status="pending",
        )
        s.add(p)
        await s.commit()
        return p.id


# --- Auth gating ----------------------------------------------------------


async def test_pending_list_requires_auth(client: AsyncClient) -> None:
    r = await client.get("/api/v1/admin/pending-prompts")
    assert r.status_code == 401


async def test_pending_list_requires_admin(client: AsyncClient) -> None:
    await _make_regular(client)
    r = await client.get("/api/v1/admin/pending-prompts")
    assert r.status_code == 403


async def test_approve_requires_admin(client: AsyncClient) -> None:
    uid = await _make_regular(client)
    pid = await _seed_pending(uid)
    r = await client.post(f"/api/v1/admin/prompts/{pid}/approve")
    assert r.status_code == 403


async def test_reject_requires_admin(client: AsyncClient) -> None:
    uid = await _make_regular(client)
    pid = await _seed_pending(uid)
    r = await client.post(f"/api/v1/admin/prompts/{pid}/reject", json={})
    assert r.status_code == 403


# --- Admin happy path ------------------------------------------------------


async def test_admin_lists_only_pending(client: AsyncClient) -> None:
    # Make an author user with two prompts: pending + published
    async with session_scope() as s:
        author = User(
            email="author@x.dev",
            password_hash=hash_password("p"),
            email_verified=True,
        )
        s.add(author)
        await s.flush()
        cat = (await s.scalars(select(PromptCategory).where(PromptCategory.slug == "code"))).one()
        s.add_all(
            [
                Prompt(
                    slug="qa",
                    title="QA Pending",
                    body="b",
                    category_id=cat.id,
                    tags=[],
                    author_user_id=author.id,
                    language="zh",
                    status="pending",
                ),
                Prompt(
                    slug="qb",
                    title="QB Published",
                    body="b",
                    category_id=cat.id,
                    tags=[],
                    author_user_id=author.id,
                    language="zh",
                    status="published",
                ),
            ]
        )
        await s.commit()

    await _make_admin(client)
    r = await client.get("/api/v1/admin/pending-prompts")
    assert r.status_code == 200
    titles = {p["title"] for p in r.json()}
    assert titles == {"QA Pending"}


async def test_approve_flips_status_to_published(client: AsyncClient) -> None:
    author_id = await _make_regular(client, email="author@x.dev")
    pid = await _seed_pending(author_id, title="ApproveMe")
    await client.post("/api/v1/auth/logout")

    await _make_admin(client)
    r = await client.post(f"/api/v1/admin/prompts/{pid}/approve")
    assert r.status_code == 200
    assert r.json()["status"] == "published"
    async with session_scope() as s:
        p = await s.get(Prompt, pid)
        assert p is not None
        assert p.status == "published"


async def test_reject_saves_review_note(client: AsyncClient) -> None:
    author_id = await _make_regular(client, email="author@x.dev")
    pid = await _seed_pending(author_id, title="RejectMe")
    await client.post("/api/v1/auth/logout")

    await _make_admin(client)
    r = await client.post(
        f"/api/v1/admin/prompts/{pid}/reject",
        json={"review_note": "Too generic"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"
    assert r.json()["review_note"] == "Too generic"
    async with session_scope() as s:
        p = await s.get(Prompt, pid)
        assert p is not None
        assert p.status == "rejected"
        assert p.review_note == "Too generic"


async def test_approve_404_for_unknown_prompt(client: AsyncClient) -> None:
    await _make_admin(client)
    r = await client.post("/api/v1/admin/prompts/9999/approve")
    assert r.status_code == 404


# --- Admin page ------------------------------------------------------------


async def test_admin_queue_page_redirects_anon(client: AsyncClient) -> None:
    r = await client.get("/admin/queue")
    assert r.status_code == 303


async def test_admin_queue_page_403_for_non_admin(client: AsyncClient) -> None:
    await _make_regular(client)
    r = await client.get("/admin/queue")
    assert r.status_code == 403


async def test_admin_queue_page_lists_pending(client: AsyncClient) -> None:
    author_id = await _make_regular(client, email="author@x.dev")
    await _seed_pending(author_id, title="QueueShown")
    await client.post("/api/v1/auth/logout")
    await _make_admin(client)

    r = await client.get("/admin/queue")
    assert r.status_code == 200
    assert "QueueShown" in r.text
    assert "author@x.dev" in r.text
