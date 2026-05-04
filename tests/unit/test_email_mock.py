from app.services.email import MockEmailBackend, send_email


async def test_mock_records_sent_email() -> None:
    MockEmailBackend.reset()
    await send_email(to="x@y.dev", subject="Hi", html="<p>h</p>", text="h")
    assert len(MockEmailBackend.sent) == 1
    sent = MockEmailBackend.sent[0]
    assert sent.to == "x@y.dev"
    assert sent.subject == "Hi"
    assert sent.html == "<p>h</p>"
    assert sent.text == "h"


async def test_mock_reset_clears_history() -> None:
    await send_email(to="a@b.dev", subject="A", html="a", text="a")
    assert len(MockEmailBackend.sent) >= 1
    MockEmailBackend.reset()
    assert MockEmailBackend.sent == []
