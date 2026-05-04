from httpx import AsyncClient
from sqlalchemy import select

from app.db import session_scope
from app.models import EmailVerificationToken
from app.services.email import MockEmailBackend


async def test_register_sends_verification_email(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": "v1@x.dev", "password": "passw0rd!"},
    )
    assert r.status_code == 201
    assert any(m.to == "v1@x.dev" and "verify" in m.subject.lower() for m in MockEmailBackend.sent)


async def test_register_email_contains_verification_link(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={"email": "v1b@x.dev", "password": "passw0rd!"},
    )
    msg = next(m for m in MockEmailBackend.sent if m.to == "v1b@x.dev")
    # Both html and plaintext branches contain the verify URL
    assert "/verify-email/" in msg.html
    assert "/verify-email/" in msg.text


async def test_verify_email_marks_user_verified(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={"email": "v2@x.dev", "password": "passw0rd!"},
    )
    async with session_scope() as s:
        token = (await s.execute(select(EmailVerificationToken))).scalar_one().token
    r = await client.post(f"/api/v1/auth/verify-email/{token}")
    assert r.status_code == 200
    # User is now verified — login + /me should reflect it.
    await client.post(
        "/api/v1/auth/login",
        json={"email": "v2@x.dev", "password": "passw0rd!"},
    )
    me = await client.get("/api/v1/me")
    assert me.json()["email_verified"] is True


async def test_verify_email_invalid_token_404(client: AsyncClient) -> None:
    r = await client.post("/api/v1/auth/verify-email/invalid-token-xyz")
    assert r.status_code == 404


async def test_verify_email_token_is_one_shot(client: AsyncClient) -> None:
    """Once consumed, the same token can't be re-used."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": "v3@x.dev", "password": "passw0rd!"},
    )
    async with session_scope() as s:
        token = (await s.execute(select(EmailVerificationToken))).scalar_one().token
    first = await client.post(f"/api/v1/auth/verify-email/{token}")
    assert first.status_code == 200
    second = await client.post(f"/api/v1/auth/verify-email/{token}")
    assert second.status_code == 404
