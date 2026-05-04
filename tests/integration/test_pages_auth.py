from httpx import AsyncClient
from sqlalchemy import select

from app.db import session_scope
from app.models import User


async def test_login_page_renders(client: AsyncClient) -> None:
    r = await client.get("/login")
    assert r.status_code == 200
    assert "<form" in r.text
    assert 'name="email"' in r.text


async def test_register_page_renders(client: AsyncClient) -> None:
    r = await client.get("/register")
    assert r.status_code == 200
    assert "Register" in r.text or "注册" in r.text
    assert "<form" in r.text


async def test_forgot_password_page_renders(client: AsyncClient) -> None:
    r = await client.get("/forgot-password")
    assert r.status_code == 200
    assert "<form" in r.text


async def test_reset_password_page_renders(client: AsyncClient) -> None:
    r = await client.get("/reset-password/some-token-xyz")
    assert r.status_code == 200
    assert "<form" in r.text
    # Token should be embedded in the form (hidden field)
    assert "some-token-xyz" in r.text


async def test_register_form_post_redirects(client: AsyncClient) -> None:
    r = await client.post(
        "/register",
        data={"email": "f1@x.dev", "password": "passw0rd!", "display_name": "F"},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    # User actually got created
    async with session_scope() as s:
        user = (await s.execute(select(User).where(User.email == "f1@x.dev"))).scalar_one_or_none()
    assert user is not None


async def test_register_form_post_duplicate_renders_error(client: AsyncClient) -> None:
    await client.post(
        "/register",
        data={"email": "f2@x.dev", "password": "passw0rd!"},
        follow_redirects=False,
    )
    r = await client.post(
        "/register",
        data={"email": "f2@x.dev", "password": "passw0rd!"},
        follow_redirects=False,
    )
    assert r.status_code == 409
    assert "already registered" in r.text.lower() or "已注册" in r.text


async def test_login_form_post_sets_cookie_and_redirects(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={"email": "f3@x.dev", "password": "passw0rd!"},
    )
    r = await client.post(
        "/login",
        data={"email": "f3@x.dev", "password": "passw0rd!"},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    assert "session" in r.cookies


async def test_login_form_post_bad_creds_renders_error(client: AsyncClient) -> None:
    r = await client.post(
        "/login",
        data={"email": "nope@x.dev", "password": "passw0rd!"},
        follow_redirects=False,
    )
    assert r.status_code == 401
    assert "<form" in r.text  # re-renders the form


async def test_verify_pending_page_renders(client: AsyncClient) -> None:
    r = await client.get("/verify-pending?email=hello@x.dev")
    assert r.status_code == 200
    assert "hello@x.dev" in r.text
