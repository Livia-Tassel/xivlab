from httpx import AsyncClient
from sqlalchemy import select

from app.db import session_scope
from app.models import PasswordResetToken
from app.services.email import MockEmailBackend


async def test_forgot_password_sends_email(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={"email": "p1@x.dev", "password": "old123!!"},
    )
    MockEmailBackend.reset()
    r = await client.post("/api/v1/auth/forgot-password", json={"email": "p1@x.dev"})
    assert r.status_code == 200
    assert any(m.to == "p1@x.dev" and "reset" in m.subject.lower() for m in MockEmailBackend.sent)


async def test_reset_password_changes_password(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={"email": "p2@x.dev", "password": "old1234!"},
    )
    await client.post("/api/v1/auth/forgot-password", json={"email": "p2@x.dev"})
    async with session_scope() as s:
        tok = (await s.execute(select(PasswordResetToken))).scalars().first()
    assert tok is not None
    token = tok.token

    r = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": "new1234!"},
    )
    assert r.status_code == 200

    # New password works
    r1 = await client.post(
        "/api/v1/auth/login",
        json={"email": "p2@x.dev", "password": "new1234!"},
    )
    assert r1.status_code == 200

    # Old password no longer works
    r2 = await client.post(
        "/api/v1/auth/login",
        json={"email": "p2@x.dev", "password": "old1234!"},
    )
    assert r2.status_code == 401


async def test_forgot_unknown_email_silent(client: AsyncClient) -> None:
    """Anti-enumeration: 200 even when the email isn't registered, no email dispatched."""
    r = await client.post("/api/v1/auth/forgot-password", json={"email": "ghost@x.dev"})
    assert r.status_code == 200
    assert not any(m.to == "ghost@x.dev" for m in MockEmailBackend.sent)


async def test_reset_password_invalid_token_404(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": "bogus-token", "new_password": "new1234!"},
    )
    assert r.status_code == 404


async def test_reset_password_token_is_one_shot(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={"email": "p3@x.dev", "password": "old1234!"},
    )
    await client.post("/api/v1/auth/forgot-password", json={"email": "p3@x.dev"})
    async with session_scope() as s:
        tok = (await s.execute(select(PasswordResetToken))).scalars().first()
    assert tok is not None
    token = tok.token

    first = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": "new1234!"},
    )
    assert first.status_code == 200
    second = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": "another12!"},
    )
    assert second.status_code == 404


async def test_reset_password_short_password_422(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": "any", "new_password": "x"},
    )
    assert r.status_code == 422
