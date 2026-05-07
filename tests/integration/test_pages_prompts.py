"""Server-rendered PromptHub pages: home + category."""

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
