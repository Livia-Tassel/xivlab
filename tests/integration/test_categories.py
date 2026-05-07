"""Tests for the public categories list endpoint."""

from httpx import AsyncClient


async def test_list_categories_returns_all_seeded(client: AsyncClient) -> None:
    r = await client.get("/api/v1/categories")
    assert r.status_code == 200
    cats = r.json()
    assert len(cats) == 9
    slugs = [c["slug"] for c in cats]
    assert "paper-writing" in slugs
    assert "code" in slugs


async def test_list_categories_sorted_by_sort_order(client: AsyncClient) -> None:
    r = await client.get("/api/v1/categories")
    cats = r.json()
    assert cats[0]["slug"] == "paper-writing"  # sort_order = 10
    assert cats[-1]["slug"] == "misc"  # sort_order = 90


async def test_list_categories_includes_metadata(client: AsyncClient) -> None:
    r = await client.get("/api/v1/categories")
    first = r.json()[0]
    assert set(first.keys()) == {"slug", "name", "description", "icon"}
    assert first["name"]
    assert first["icon"]


async def test_list_categories_no_auth_required(client: AsyncClient) -> None:
    r = await client.get("/api/v1/categories")
    assert r.status_code == 200
