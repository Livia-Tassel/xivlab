"""Server-rendered PromptHub pages: home + category + detail + dashboard."""

from httpx import AsyncClient
from sqlalchemy import select

from app.db import session_scope
from app.models import Prompt, PromptCategory, User
from app.services.password import hash_password


async def _seed_user_and_prompt(
    *,
    title: str,
    category_slug: str = "paper-writing",
    status: str = "published",
    upvotes: int = 0,
    body: str = "body text",
    description: str | None = "desc",
    email: str = "author@x.dev",
) -> int:
    async with session_scope() as s:
        user = (await s.scalars(select(User).where(User.email == email))).one_or_none()
        if user is None:
            user = User(
                email=email,
                password_hash=hash_password("passw0rd!"),
                email_verified=True,
            )
            s.add(user)
            await s.flush()
        cat = (
            await s.scalars(select(PromptCategory).where(PromptCategory.slug == category_slug))
        ).one()
        from app.services.slug import slugify

        p = Prompt(
            slug=slugify(title) + f"-{user.id}-{title}"[:8],
            title=title,
            description=description,
            body=body,
            category_id=cat.id,
            tags=[],
            author_user_id=user.id,
            language="zh",
            upvotes=upvotes,
            status=status,
        )
        s.add(p)
        await s.commit()
        return p.id


async def test_home_page_renders_with_categories(client: AsyncClient) -> None:
    r = await client.get("/")
    assert r.status_code == 200
    body = r.text
    assert "PromptHub" in body
    # All 9 categories appear by name
    assert "论文写作" in body
    assert "代码" in body


async def test_home_page_shows_top_published_prompts_per_category(
    client: AsyncClient,
) -> None:
    await _seed_user_and_prompt(title="Top1", upvotes=50)
    await _seed_user_and_prompt(title="Top2", upvotes=10)
    await _seed_user_and_prompt(title="Hidden", status="pending", upvotes=999)

    r = await client.get("/")
    assert r.status_code == 200
    assert "Top1" in r.text
    assert "Top2" in r.text
    assert "Hidden" not in r.text


async def test_home_page_caps_at_5_per_category(client: AsyncClient) -> None:
    for i in range(7):
        await _seed_user_and_prompt(title=f"Pcap{i}", upvotes=100 - i)
    r = await client.get("/")
    # First 5 by upvotes appear; last 2 don't
    for i in range(5):
        assert f"Pcap{i}" in r.text
    assert "Pcap6" not in r.text


async def test_category_page_404_for_unknown_slug(client: AsyncClient) -> None:
    r = await client.get("/c/not-a-real-cat")
    assert r.status_code == 404


async def test_category_page_lists_published_prompts(client: AsyncClient) -> None:
    await _seed_user_and_prompt(title="CatPub", category_slug="code")
    await _seed_user_and_prompt(title="CatHidden", category_slug="code", status="pending")
    await _seed_user_and_prompt(title="OtherCat", category_slug="paper-writing")

    r = await client.get("/c/code")
    assert r.status_code == 200
    assert "CatPub" in r.text
    assert "CatHidden" not in r.text
    assert "OtherCat" not in r.text


async def test_category_page_sort_hot_orders_by_upvotes(client: AsyncClient) -> None:
    await _seed_user_and_prompt(title="LowVotes", category_slug="code", upvotes=1)
    await _seed_user_and_prompt(title="HighVotes", category_slug="code", upvotes=99)

    r = await client.get("/c/code", params={"sort": "hot"})
    body = r.text
    assert body.index("HighVotes") < body.index("LowVotes")


async def test_category_page_sort_new_orders_by_created_desc(client: AsyncClient) -> None:
    first = await _seed_user_and_prompt(title="OlderOne", category_slug="code")
    second = await _seed_user_and_prompt(title="NewerOne", category_slug="code")
    assert first < second  # IDs ascend with created_at

    r = await client.get("/c/code", params={"sort": "new"})
    body = r.text
    assert body.index("NewerOne") < body.index("OlderOne")


# --- Detail page ---------------------------------------------------------


async def test_detail_page_404_for_unknown_slug(client: AsyncClient) -> None:
    r = await client.get("/p/no-such-prompt")
    assert r.status_code == 404


async def test_detail_page_renders_published_prompt(client: AsyncClient) -> None:
    pid = await _seed_user_and_prompt(title="MyDetail", description="A nice prompt")
    async with session_scope() as s:
        slug = (await s.get(Prompt, pid)).slug

    r = await client.get(f"/p/{slug}")
    assert r.status_code == 200
    body = r.text
    assert "MyDetail" in body
    assert "A nice prompt" in body
    # Body content rendered
    assert "body text" in body


async def test_detail_page_increments_views(client: AsyncClient) -> None:
    pid = await _seed_user_and_prompt(title="ViewBump")
    async with session_scope() as s:
        slug = (await s.get(Prompt, pid)).slug

    await client.get(f"/p/{slug}")
    await client.get(f"/p/{slug}")

    async with session_scope() as s:
        p = await s.get(Prompt, pid)
        assert p is not None
        assert p.views == 2


async def test_detail_page_pending_404_for_anon(client: AsyncClient) -> None:
    pid = await _seed_user_and_prompt(title="HiddenPending", status="pending")
    async with session_scope() as s:
        slug = (await s.get(Prompt, pid)).slug
    r = await client.get(f"/p/{slug}")
    assert r.status_code == 404


# --- Dashboard / form ---------------------------------------------------


async def _login_verified(client: AsyncClient, email: str = "user@x.dev") -> int:
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


async def test_dashboard_prompts_redirects_when_logged_out(client: AsyncClient) -> None:
    r = await client.get("/dashboard/prompts")
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


async def test_dashboard_prompts_lists_user_own_prompts(client: AsyncClient) -> None:
    uid = await _login_verified(client, email="me@x.dev")
    # Mine
    async with session_scope() as s:
        cat = (await s.scalars(select(PromptCategory).where(PromptCategory.slug == "code"))).one()
        s.add(
            Prompt(
                slug="mine-1",
                title="MineOne",
                body="x",
                category_id=cat.id,
                tags=[],
                author_user_id=uid,
                language="zh",
                status="pending",
            )
        )
        # Someone else's
        other = User(email="other@x.dev", password_hash=hash_password("p"), email_verified=True)
        s.add(other)
        await s.flush()
        s.add(
            Prompt(
                slug="theirs-1",
                title="TheirsOne",
                body="x",
                category_id=cat.id,
                tags=[],
                author_user_id=other.id,
                language="zh",
                status="published",
            )
        )
        await s.commit()

    r = await client.get("/dashboard/prompts")
    assert r.status_code == 200
    assert "MineOne" in r.text
    assert "TheirsOne" not in r.text


async def test_dashboard_shows_status_badges_and_review_note(client: AsyncClient) -> None:
    uid = await _login_verified(client, email="me@x.dev")
    async with session_scope() as s:
        cat = (await s.scalars(select(PromptCategory).where(PromptCategory.slug == "code"))).one()
        s.add(
            Prompt(
                slug="rejected-1",
                title="GotRejected",
                body="x",
                category_id=cat.id,
                tags=[],
                author_user_id=uid,
                language="zh",
                status="rejected",
                review_note="Not specific enough",
            )
        )
        await s.commit()
    r = await client.get("/dashboard/prompts")
    assert "rejected" in r.text
    assert "Not specific enough" in r.text


async def test_new_prompt_form_renders_for_verified_user(client: AsyncClient) -> None:
    await _login_verified(client, email="poster@x.dev")
    r = await client.get("/dashboard/prompts/new")
    assert r.status_code == 200
    assert "Submit" in r.text or "submit" in r.text
    # Categories listed
    assert "论文写作" in r.text


async def test_create_prompt_form_submit(client: AsyncClient) -> None:
    uid = await _login_verified(client, email="poster@x.dev")
    r = await client.post(
        "/dashboard/prompts",
        data={
            "title": "From form",
            "body": "Body here",
            "category_slug": "code",
            "language": "zh",
        },
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/dashboard/prompts"
    async with session_scope() as s:
        rows = (await s.scalars(select(Prompt).where(Prompt.author_user_id == uid))).all()
        assert len(rows) == 1
        assert rows[0].title == "From form"
        assert rows[0].status == "pending"


async def test_edit_prompt_resets_status_to_pending(client: AsyncClient) -> None:
    uid = await _login_verified(client, email="poster@x.dev")
    async with session_scope() as s:
        cat = (await s.scalars(select(PromptCategory).where(PromptCategory.slug == "code"))).one()
        p = Prompt(
            slug="ep-1",
            title="Old",
            body="x",
            category_id=cat.id,
            tags=[],
            author_user_id=uid,
            language="zh",
            status="published",
        )
        s.add(p)
        await s.commit()
        pid = p.id

    r = await client.post(
        f"/dashboard/prompts/{pid}",
        data={
            "title": "Updated",
            "body": "yy",
            "category_slug": "code",
            "language": "zh",
        },
    )
    assert r.status_code == 303
    async with session_scope() as s:
        p = await s.get(Prompt, pid)
        assert p is not None
        assert p.title == "Updated"
        assert p.status == "pending"


async def test_delete_prompt_form_marks_deleted(client: AsyncClient) -> None:
    uid = await _login_verified(client, email="poster@x.dev")
    async with session_scope() as s:
        cat = (await s.scalars(select(PromptCategory).where(PromptCategory.slug == "code"))).one()
        p = Prompt(
            slug="dp-1",
            title="X",
            body="x",
            category_id=cat.id,
            tags=[],
            author_user_id=uid,
            language="zh",
            status="published",
        )
        s.add(p)
        await s.commit()
        pid = p.id

    r = await client.post(f"/dashboard/prompts/{pid}/delete")
    assert r.status_code == 303
    async with session_scope() as s:
        p = await s.get(Prompt, pid)
        assert p is not None
        assert p.status == "deleted"
