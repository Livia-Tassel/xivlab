"""Email backends: mock for tests/dev, Resend for prod.

Backend selection is driven by ``settings.email_backend``:
- ``"mock"`` (default in tests/dev) — records sent emails on
  :class:`MockEmailBackend.sent` for assertion.
- ``"resend"`` — calls the Resend HTTP API via its native async client.
"""

from dataclasses import dataclass
from typing import ClassVar

from app.config import get_settings


@dataclass(frozen=True)
class SentEmail:
    to: str
    subject: str
    html: str
    text: str


class MockEmailBackend:
    """Class-level singleton recording every email a test would have sent."""

    sent: ClassVar[list[SentEmail]] = []

    @classmethod
    def reset(cls) -> None:
        cls.sent.clear()

    @classmethod
    async def send(cls, to: str, subject: str, html: str, text: str) -> None:
        cls.sent.append(SentEmail(to=to, subject=subject, html=html, text=text))


class ResendBackend:
    @classmethod
    async def send(cls, to: str, subject: str, html: str, text: str) -> None:
        import resend  # lazy import so test envs without API keys don't need it

        settings = get_settings()
        resend.api_key = settings.resend_api_key
        params: resend.Emails.SendParams = {
            "from": settings.resend_from_email,
            "to": [to],
            "subject": subject,
            "html": html,
            "text": text,
        }
        await resend.Emails.send_async(params)


def get_backend() -> type[MockEmailBackend] | type[ResendBackend]:
    settings = get_settings()
    if settings.email_backend == "resend":
        return ResendBackend
    return MockEmailBackend


async def send_email(to: str, subject: str, html: str, text: str) -> None:
    backend = get_backend()
    await backend.send(to=to, subject=subject, html=html, text=text)
