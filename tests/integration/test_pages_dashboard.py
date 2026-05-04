from httpx import AsyncClient
from sqlalchemy import select

from app.db import session_scope
from app.models import Task, User


async def _make_verified_user(client: AsyncClient, email: str = "d@x.dev") -> None:
    """Register, force-verify, and log in. Cookies persist on `client`."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "passw0rd!"},
    )
    async with session_scope() as s:
        u = (await s.execute(select(User).where(User.email == email))).scalar_one()
        u.email_verified = True
        await s.commit()
    await client.post("/api/v1/auth/login", json={"email": email, "password": "passw0rd!"})


async def test_dashboard_requires_login(client: AsyncClient) -> None:
    r = await client.get("/dashboard", follow_redirects=False)
    assert r.status_code in (302, 303)
    assert "/login" in r.headers.get("location", "")


async def test_dashboard_unverified_redirects_to_verify_pending(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={"email": "uv2@x.dev", "password": "passw0rd!"},
    )
    await client.post("/api/v1/auth/login", json={"email": "uv2@x.dev", "password": "passw0rd!"})
    r = await client.get("/dashboard", follow_redirects=False)
    assert r.status_code in (302, 303)
    assert "/verify-pending" in r.headers.get("location", "")


async def test_dashboard_verified_empty_state(client: AsyncClient) -> None:
    await _make_verified_user(client)
    r = await client.get("/dashboard")
    assert r.status_code == 200
    assert "No tasks" in r.text or "0/2" in r.text


async def test_dashboard_lists_user_tasks(client: AsyncClient) -> None:
    await _make_verified_user(client)
    await client.post(
        "/api/v1/tasks",
        json={
            "name": "LLM agents",
            "arxiv_categories": ["cs.AI", "cs.LG"],
            "keywords": ["LLM agent"],
        },
    )
    r = await client.get("/dashboard")
    assert r.status_code == 200
    assert "LLM agents" in r.text
    assert "cs.AI" in r.text


async def test_new_task_page_renders(client: AsyncClient) -> None:
    await _make_verified_user(client)
    r = await client.get("/dashboard/tasks/new")
    assert r.status_code == 200
    assert "<form" in r.text
    assert 'name="name"' in r.text
    assert 'name="arxiv_categories"' in r.text


async def test_dashboard_create_task_via_form(client: AsyncClient) -> None:
    await _make_verified_user(client)
    r = await client.post(
        "/dashboard/tasks",
        data={
            "name": "From form",
            "arxiv_categories": "cs.AI, cs.LG",
            "keywords": "agents, tools",
            "interest_description": "novel multi-agent systems",
            "max_papers_per_day": "8",
            "delivery_time": "09:30",
            "delivery_channels": ["email", "rss"],
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    assert r.headers.get("location") == "/dashboard"

    async with session_scope() as s:
        task = (await s.execute(select(Task).where(Task.name == "From form"))).scalar_one_or_none()
    assert task is not None
    assert task.arxiv_categories == ["cs.AI", "cs.LG"]
    assert task.keywords == ["agents", "tools"]
    assert task.delivery_time == "09:30"
    assert task.max_papers_per_day == 8
    assert set(task.delivery_channels) == {"email", "rss"}


async def test_dashboard_edit_form_prefilled(client: AsyncClient) -> None:
    await _make_verified_user(client)
    create = await client.post(
        "/api/v1/tasks",
        json={"name": "Editable", "arxiv_categories": ["cs.CL"]},
    )
    tid = create.json()["id"]
    r = await client.get(f"/dashboard/tasks/{tid}")
    assert r.status_code == 200
    assert 'value="Editable"' in r.text
    assert "cs.CL" in r.text


async def test_dashboard_update_task_via_form(client: AsyncClient) -> None:
    await _make_verified_user(client)
    create = await client.post(
        "/api/v1/tasks",
        json={"name": "old", "arxiv_categories": ["cs.AI"]},
    )
    tid = create.json()["id"]
    r = await client.post(
        f"/dashboard/tasks/{tid}",
        data={
            "name": "new",
            "arxiv_categories": "cs.AI, cs.CV",
            "keywords": "",
            "interest_description": "",
            "max_papers_per_day": "10",
            "delivery_time": "08:00",
            "delivery_channels": ["email"],
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    async with session_scope() as s:
        task = (await s.execute(select(Task).where(Task.id == tid))).scalar_one()
    assert task.name == "new"
    assert task.arxiv_categories == ["cs.AI", "cs.CV"]


async def test_dashboard_delete_task_via_form(client: AsyncClient) -> None:
    await _make_verified_user(client)
    create = await client.post(
        "/api/v1/tasks", json={"name": "doomed", "arxiv_categories": ["cs.AI"]}
    )
    tid = create.json()["id"]
    r = await client.post(f"/dashboard/tasks/{tid}/delete", follow_redirects=False)
    assert r.status_code in (302, 303)
    async with session_scope() as s:
        task = (await s.execute(select(Task).where(Task.id == tid))).scalar_one_or_none()
    assert task is None


async def test_dashboard_other_users_task_404(client: AsyncClient) -> None:
    await _make_verified_user(client, "owner@x.dev")
    create = await client.post(
        "/api/v1/tasks", json={"name": "private", "arxiv_categories": ["cs.AI"]}
    )
    tid = create.json()["id"]
    await client.post("/api/v1/auth/logout")
    await _make_verified_user(client, "snoop@x.dev")
    r = await client.get(f"/dashboard/tasks/{tid}")
    assert r.status_code == 404


async def test_dashboard_quota_hides_new_button(client: AsyncClient) -> None:
    await _make_verified_user(client)
    for i in range(2):
        await client.post(
            "/api/v1/tasks",
            json={"name": f"t{i}", "arxiv_categories": ["cs.AI"]},
        )
    r = await client.get("/dashboard")
    assert r.status_code == 200
    # When at quota, the "New task" button should NOT be visible
    assert "/dashboard/tasks/new" not in r.text


async def test_dashboard_create_form_invalid_re_renders(client: AsyncClient) -> None:
    await _make_verified_user(client)
    r = await client.post(
        "/dashboard/tasks",
        data={
            "name": "no categories",
            "arxiv_categories": "  ",  # empty after CSV-split → TaskCreate validator fails
            "keywords": "",
            "interest_description": "",
            "max_papers_per_day": "10",
            "delivery_time": "08:00",
            "delivery_channels": ["email"],
        },
        follow_redirects=False,
    )
    assert r.status_code == 422
    assert "<form" in r.text
