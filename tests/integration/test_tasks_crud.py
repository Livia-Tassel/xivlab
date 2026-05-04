from httpx import AsyncClient
from sqlalchemy import select

from app.db import session_scope
from app.models import User


async def _make_verified_user(client: AsyncClient, email: str = "tu@x.dev") -> None:
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


async def test_create_task(client: AsyncClient) -> None:
    await _make_verified_user(client)
    r = await client.post(
        "/api/v1/tasks",
        json={
            "name": "LLM agents",
            "arxiv_categories": ["cs.AI", "cs.LG"],
            "keywords": ["LLM agent", "tool use"],
        },
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["name"] == "LLM agents"
    assert data["arxiv_categories"] == ["cs.AI", "cs.LG"]
    assert data["keywords"] == ["LLM agent", "tool use"]
    assert data["enabled"] is True
    assert "rss_token" in data
    assert len(data["rss_token"]) >= 32
    assert data["delivery_channels"] == ["email"]
    assert data["max_papers_per_day"] == 10
    assert data["delivery_time"] == "08:00"


async def test_quota_blocks_third_task(client: AsyncClient) -> None:
    await _make_verified_user(client)
    for i in range(2):
        r = await client.post(
            "/api/v1/tasks",
            json={"name": f"t{i}", "arxiv_categories": ["cs.AI"]},
        )
        assert r.status_code == 201, f"task {i} failed: {r.text}"
    r3 = await client.post(
        "/api/v1/tasks",
        json={"name": "t3", "arxiv_categories": ["cs.AI"]},
    )
    assert r3.status_code == 403
    assert "limit" in r3.json()["detail"].lower()


async def test_list_only_own_tasks(client: AsyncClient) -> None:
    await _make_verified_user(client, "owner@x.dev")
    await client.post(
        "/api/v1/tasks",
        json={"name": "mine", "arxiv_categories": ["cs.AI"]},
    )
    await client.post("/api/v1/auth/logout")
    await _make_verified_user(client, "other@x.dev")
    r = await client.get("/api/v1/tasks")
    assert r.status_code == 200
    names = [t["name"] for t in r.json()]
    assert "mine" not in names


async def test_unverified_cannot_create(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={"email": "uv@x.dev", "password": "passw0rd!"},
    )
    await client.post("/api/v1/auth/login", json={"email": "uv@x.dev", "password": "passw0rd!"})
    r = await client.post(
        "/api/v1/tasks",
        json={"name": "x", "arxiv_categories": ["cs.AI"]},
    )
    assert r.status_code == 403


async def test_unauthenticated_cannot_list(client: AsyncClient) -> None:
    r = await client.get("/api/v1/tasks")
    assert r.status_code == 401


async def test_get_single_task(client: AsyncClient) -> None:
    await _make_verified_user(client)
    create = await client.post("/api/v1/tasks", json={"name": "G", "arxiv_categories": ["cs.AI"]})
    tid = create.json()["id"]
    r = await client.get(f"/api/v1/tasks/{tid}")
    assert r.status_code == 200
    assert r.json()["name"] == "G"


async def test_get_other_users_task_404(client: AsyncClient) -> None:
    await _make_verified_user(client, "a@x.dev")
    create = await client.post(
        "/api/v1/tasks", json={"name": "secret", "arxiv_categories": ["cs.AI"]}
    )
    tid = create.json()["id"]
    await client.post("/api/v1/auth/logout")
    await _make_verified_user(client, "b@x.dev")
    r = await client.get(f"/api/v1/tasks/{tid}")
    assert r.status_code == 404


async def test_patch_updates_fields(client: AsyncClient) -> None:
    await _make_verified_user(client)
    create = await client.post(
        "/api/v1/tasks",
        json={"name": "old", "arxiv_categories": ["cs.AI"]},
    )
    tid = create.json()["id"]
    r = await client.patch(
        f"/api/v1/tasks/{tid}",
        json={"name": "new", "max_papers_per_day": 5, "enabled": False},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "new"
    assert body["max_papers_per_day"] == 5
    assert body["enabled"] is False
    # Untouched fields remain
    assert body["arxiv_categories"] == ["cs.AI"]


async def test_delete_task(client: AsyncClient) -> None:
    await _make_verified_user(client)
    create = await client.post(
        "/api/v1/tasks", json={"name": "doomed", "arxiv_categories": ["cs.AI"]}
    )
    tid = create.json()["id"]
    r = await client.delete(f"/api/v1/tasks/{tid}")
    assert r.status_code == 204
    r2 = await client.get(f"/api/v1/tasks/{tid}")
    assert r2.status_code == 404


async def test_regenerate_rss_token(client: AsyncClient) -> None:
    await _make_verified_user(client)
    create = await client.post("/api/v1/tasks", json={"name": "t", "arxiv_categories": ["cs.AI"]})
    tid = create.json()["id"]
    old = create.json()["rss_token"]
    r = await client.post(f"/api/v1/tasks/{tid}/regenerate-rss-token")
    assert r.status_code == 200
    assert r.json()["rss_token"] != old
    assert len(r.json()["rss_token"]) >= 32


async def test_create_rejects_empty_categories(client: AsyncClient) -> None:
    await _make_verified_user(client)
    r = await client.post(
        "/api/v1/tasks",
        json={"name": "x", "arxiv_categories": []},
    )
    assert r.status_code == 422


async def test_create_rejects_invalid_channel(client: AsyncClient) -> None:
    await _make_verified_user(client)
    r = await client.post(
        "/api/v1/tasks",
        json={
            "name": "x",
            "arxiv_categories": ["cs.AI"],
            "delivery_channels": ["sms"],
        },
    )
    assert r.status_code == 422


async def test_create_rejects_bad_delivery_time(client: AsyncClient) -> None:
    await _make_verified_user(client)
    r = await client.post(
        "/api/v1/tasks",
        json={
            "name": "x",
            "arxiv_categories": ["cs.AI"],
            "delivery_time": "8am",
        },
    )
    assert r.status_code == 422
