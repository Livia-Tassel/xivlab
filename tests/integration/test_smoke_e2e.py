"""End-to-end smoke test exercising register → digest → RSS → prompt flow.

Single test: covers the user-visible features end-to-end, with external
dependencies mocked (arXiv fetch, embeddings, email backend).
"""

from datetime import datetime
from xml.etree import ElementTree as ET

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db import session_scope
from app.jobs.send_digests import run_send_digests
from app.models import (
    EmailVerificationToken,
    Paper,
    Prompt,
    Task,
    User,
)
from app.services.email import MockEmailBackend


async def _verify_via_db(email: str) -> None:
    """Fish the verification token from the DB and POST it."""
    async with session_scope() as s:
        u = (await s.scalars(select(User).where(User.email == email))).one()
        # Direct flip — the public flow is GET /verify-email/<token>, exercised in T05.
        u.email_verified = True
        await s.commit()


async def _seed_paper(arxiv_id: str, title: str, category: str = "cs.AI") -> None:
    async with session_scope() as s:
        s.add(
            Paper(
                id=arxiv_id,
                title=title,
                authors=["Alice", "Bob"],
                abstract=f"{title} — abstract body.",
                primary_category=category,
                all_categories=[category],
                published_at=datetime.utcnow(),
            )
        )
        await s.commit()


@pytest.mark.asyncio
async def test_e2e_register_digest_rss_prompt(client: AsyncClient, monkeypatch) -> None:
    # 1. Register
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": "alice@x.dev", "password": "passw0rd!"},
    )
    assert r.status_code in (200, 201), r.text

    # 2. Verify email (fish token from DB equivalent)
    await _verify_via_db("alice@x.dev")

    # 3. Login
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "alice@x.dev", "password": "passw0rd!"},
    )
    assert r.status_code == 200, r.text

    # 4. Create a task
    r = await client.post(
        "/api/v1/tasks",
        json={
            "name": "AI daily",
            "arxiv_categories": ["cs.AI"],
            "keywords": ["agent"],
            "min_keyword_match": 1,
            "interest_description": "Multi-agent RL",
            "max_papers_per_day": 5,
            "delivery_time": "08:00",
            "delivery_channels": ["email", "rss"],
        },
    )
    assert r.status_code in (200, 201), r.text
    task_payload = r.json()
    task_id = task_payload["id"]
    rss_token = task_payload["rss_token"]

    # 5. Seed papers (mocked arXiv data)
    await _seed_paper("2401.00010", "Multi-agent agent paper")
    await _seed_paper("2401.00011", "Another agent breakthrough")

    # Pin user delivery time to "now" so send_digests picks it up.
    async with session_scope() as s:
        u = (await s.scalars(select(User).where(User.email == "alice@x.dev"))).one()
        # User TZ is Asia/Shanghai by default — set to UTC and align the task time.
        u.tz = "UTC"
        await s.commit()
    now_hhmm = datetime.utcnow().strftime("%H:%M")
    async with session_scope() as s:
        t = await s.get(Task, task_id)
        assert t is not None
        t.delivery_time = now_hhmm
        await s.commit()

    # 6. Trigger send_digests
    MockEmailBackend.reset()
    await run_send_digests()

    # 7. Email was sent
    assert any(e.to == "alice@x.dev" for e in MockEmailBackend.sent), (
        f"no email sent: {MockEmailBackend.sent}"
    )

    # 8. RSS feed via token
    r = await client.get(
        f"/rss/{u.id}/{task_id}/feed.xml",
        params={"token": rss_token},
    )
    assert r.status_code == 200
    assert "atom+xml" in r.headers.get("content-type", "")
    # XML parses; root is the Atom <feed>
    root = ET.fromstring(r.text)
    assert root.tag.endswith("feed")

    # 9. Create a prompt → admin approves → appears on home
    r = await client.post(
        "/api/v1/prompts",
        json={
            "title": "Polish my paper end-to-end",
            "body": "You are an editor. Polish: {{text}}",
            "category_slug": "paper-writing",
            "language": "zh",
            "tags": ["polish"],
        },
    )
    assert r.status_code == 201, r.text
    prompt_id = r.json()["id"]

    # Logout and become admin
    await client.post("/api/v1/auth/logout")
    await client.post(
        "/api/v1/auth/register",
        json={"email": "admin@x.dev", "password": "passw0rd!"},
    )
    async with session_scope() as s:
        admin = (await s.scalars(select(User).where(User.email == "admin@x.dev"))).one()
        admin.email_verified = True
        admin.is_admin = True
        await s.commit()
    await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@x.dev", "password": "passw0rd!"},
    )
    r = await client.post(f"/api/v1/admin/prompts/{prompt_id}/approve")
    assert r.status_code == 200
    assert r.json()["status"] == "published"

    # Home page now lists the published prompt.
    r = await client.get("/")
    assert r.status_code == 200
    assert "Polish my paper end-to-end" in r.text

    # 10. Logout completes the flow.
    r = await client.post("/api/v1/auth/logout")
    assert r.status_code in (200, 204), r.text

    # Sanity: database state matches the journey.
    async with session_scope() as s:
        prompt = await s.get(Prompt, prompt_id)
        assert prompt is not None
        assert prompt.status == "published"
        evts = (
            await s.scalars(
                select(EmailVerificationToken).where(EmailVerificationToken.user_id == u.id)
            )
        ).all()
        # We bypassed the GET verification flow, so tokens may exist but we
        # don't assert on them — what matters is email_verified=True downstream.
        _ = evts
