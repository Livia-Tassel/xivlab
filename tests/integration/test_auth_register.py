from httpx import AsyncClient


async def test_register_creates_unverified_user(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "alice@example.com",
            "password": "passw0rd!",
            "display_name": "Alice",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["email"] == "alice@example.com"
    assert body["email_verified"] is False
    assert body["display_name"] == "Alice"
    assert isinstance(body["id"], int)


async def test_register_duplicate_email_409(client: AsyncClient) -> None:
    first = await client.post(
        "/api/v1/auth/register",
        json={"email": "bob@example.com", "password": "passw0rd!"},
    )
    assert first.status_code == 201
    second = await client.post(
        "/api/v1/auth/register",
        json={"email": "bob@example.com", "password": "passw0rd!"},
    )
    assert second.status_code == 409


async def test_register_short_password_422(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": "c@example.com", "password": "x"},
    )
    assert r.status_code == 422


async def test_register_invalid_email_422(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": "passw0rd!"},
    )
    assert r.status_code == 422


async def test_register_password_is_not_returned(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": "secret@example.com", "password": "passw0rd!"},
    )
    assert r.status_code == 201
    body = r.json()
    assert "password" not in body
    assert "password_hash" not in body
