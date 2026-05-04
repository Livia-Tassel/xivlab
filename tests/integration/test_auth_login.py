from httpx import AsyncClient


async def _register(client: AsyncClient, email: str, password: str = "passw0rd!") -> None:
    r = await client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201, r.text


async def test_login_sets_cookie(client: AsyncClient) -> None:
    await _register(client, "u1@x.dev")
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "u1@x.dev", "password": "passw0rd!"},
    )
    assert r.status_code == 200
    assert "session" in r.cookies


async def test_login_wrong_password_401(client: AsyncClient) -> None:
    await _register(client, "u2@x.dev")
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "u2@x.dev", "password": "wrong"},
    )
    assert r.status_code == 401


async def test_login_unknown_email_401(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@x.dev", "password": "passw0rd!"},
    )
    assert r.status_code == 401


async def test_me_endpoint_requires_session(client: AsyncClient) -> None:
    r = await client.get("/api/v1/me")
    assert r.status_code == 401


async def test_me_endpoint_returns_user(client: AsyncClient) -> None:
    await _register(client, "u3@x.dev")
    await client.post(
        "/api/v1/auth/login",
        json={"email": "u3@x.dev", "password": "passw0rd!"},
    )
    r = await client.get("/api/v1/me")
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "u3@x.dev"
    assert body["email_verified"] is False


async def test_logout_clears_cookie(client: AsyncClient) -> None:
    await _register(client, "u4@x.dev")
    await client.post(
        "/api/v1/auth/login",
        json={"email": "u4@x.dev", "password": "passw0rd!"},
    )
    r = await client.post("/api/v1/auth/logout")
    assert r.status_code == 204
    r2 = await client.get("/api/v1/me")
    assert r2.status_code == 401
