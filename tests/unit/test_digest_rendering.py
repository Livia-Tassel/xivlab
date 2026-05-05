"""Tests for digest email rendering and delivery.

Rendering tests (pure, no DB) exercise the Jinja templates: every paper's
title/abstract/pdf-link appears in both HTML and text variants, author
truncation kicks in above 3 authors, empty-paper digests render without
crashing, and unsafe HTML in titles is escaped (templates are not marked
safe — Jinja autoescape is on by default for .html).

deliver_email tests (DB-backed, autouse ``_reset_db``) exercise the full
write path: MockEmailBackend records one send per call, one Delivery row
is created per paper, empty-papers short-circuits, and the email channel
name is literal 'email' so the T13 dedup filter picks it up.
"""

from datetime import date, datetime

import pytest
from sqlalchemy import select

from app.db import session_scope
from app.models import Delivery, Paper, Task, User
from app.services.digest import deliver_email, render_digest
from app.services.email import MockEmailBackend


def _paper(
    pid: str = "2401.00001",
    *,
    title: str = "My Title",
    abstract: str = "An abstract. " * 50,
    authors: list[str] | None = None,
    primary_category: str = "cs.AI",
    pdf_url: str | None = None,
) -> Paper:
    return Paper(
        id=pid,
        title=title,
        abstract=abstract,
        authors=authors or ["A", "B", "C", "D"],
        primary_category=primary_category,
        all_categories=[primary_category],
        published_at=datetime(2026, 5, 5, 12, 0, 0),
        pdf_url=pdf_url,
    )


def _task(name: str = "LLM agents") -> Task:
    return Task(
        user_id=1,
        name=name,
        arxiv_categories=["cs.AI"],
        keywords=None,
        min_keyword_match=1,
        max_papers_per_day=10,
        delivery_time="08:00",
        delivery_channels=["email"],
        rss_token="rss-token-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        enabled=True,
    )


# --- rendering ------------------------------------------------------------


def test_render_digest_returns_html_and_text() -> None:
    html, text = render_digest(_task(), [_paper()], "http://x/u")
    assert isinstance(html, str) and isinstance(text, str)
    assert html.strip().startswith("<!doctype html>") or html.strip().startswith("<!DOCTYPE")


def test_render_digest_includes_title_and_abstract_in_html_and_text() -> None:
    p = _paper(title="My Title", abstract="Concrete abstract sentence.")
    html, text = render_digest(_task(), [p], "http://x/u")
    assert "My Title" in html
    assert "Concrete abstract sentence." in html
    assert "My Title" in text
    assert "Concrete abstract sentence." in text


def test_render_digest_truncates_authors_above_three() -> None:
    p = _paper(authors=["A", "B", "C", "D", "E"])
    html, text = render_digest(_task(), [p], "http://x/u")
    assert "et al." in html
    assert "et al." in text
    # 4th/5th authors must not appear
    assert "D" not in html.split("et al.")[0].split("A, B, C")[-1]


def test_render_digest_shows_all_authors_when_three_or_fewer() -> None:
    p = _paper(authors=["Ada", "Bob", "Cid"])
    html, _ = render_digest(_task(), [p], "http://x/u")
    assert "Ada" in html and "Bob" in html and "Cid" in html
    assert "et al." not in html


def test_render_digest_links_to_arxiv_abs_and_pdf() -> None:
    p = _paper(pid="2401.12345", pdf_url=None)
    html, text = render_digest(_task(), [p], "http://x/u")
    assert "arxiv.org/abs/2401.12345" in html
    # Fallback pdf URL when pdf_url is None
    assert "arxiv.org/pdf/2401.12345" in html or "arxiv.org/abs/2401.12345" in text


def test_render_digest_uses_explicit_pdf_url_when_provided() -> None:
    p = _paper(pdf_url="https://custom.example/x.pdf")
    html, _ = render_digest(_task(), [p], "http://x/u")
    assert "https://custom.example/x.pdf" in html


def test_render_digest_includes_today_and_paper_count() -> None:
    html, text = render_digest(
        _task(name="My Task"), [_paper(), _paper("2401.00002")], "http://x/u"
    )
    today = date.today().isoformat()
    assert today in html
    assert today in text
    assert "My Task" in html
    assert "2 new papers" in html or "2 " in html  # paper count appears


def test_render_digest_includes_unsubscribe_url() -> None:
    html, _ = render_digest(_task(), [_paper()], "http://x/u/unsub-path")
    assert "http://x/u/unsub-path" in html


def test_render_digest_truncates_long_abstracts() -> None:
    """Abstracts longer than 600 chars get an ellipsis in the HTML."""
    long_abs = "word " * 500
    p = _paper(abstract=long_abs)
    html, _ = render_digest(_task(), [p], "http://x/u")
    assert "…" in html


def test_render_digest_escapes_html_in_title() -> None:
    """Autoescape must prevent title injection into the email body."""
    p = _paper(title="<script>alert('x')</script>")
    html, _ = render_digest(_task(), [p], "http://x/u")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html or "&#x3C;script&#x3E;" in html or "&#60;script&#62;" in html


def test_render_digest_empty_papers_list_does_not_crash() -> None:
    html, text = render_digest(_task(), [], "http://x/u")
    assert isinstance(html, str)
    assert isinstance(text, str)


# --- delivery -------------------------------------------------------------


async def _seed_user_and_task() -> tuple[int, int, str]:
    """Create a user + task in the DB, return (user_id, task_id, email)."""
    async with session_scope() as s:
        u = User(email="deliver@x.dev", password_hash="x", email_verified=True)
        s.add(u)
        await s.commit()
        t = Task(
            user_id=u.id,
            name="T",
            arxiv_categories=["cs.AI"],
            keywords=None,
            min_keyword_match=1,
            max_papers_per_day=10,
            delivery_time="08:00",
            delivery_channels=["email"],
            rss_token="rss-token-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            enabled=True,
        )
        s.add(t)
        s.add(_paper("2401.00001"))
        s.add(_paper("2401.00002"))
        await s.commit()
        return u.id, t.id, u.email


async def test_deliver_email_sends_one_email_and_writes_delivery_rows() -> None:
    MockEmailBackend.reset()
    user_id, task_id, email = await _seed_user_and_task()

    async with session_scope() as s:
        user = await s.get(User, user_id)
        task = await s.get(Task, task_id)
        papers = [
            (await s.get(Paper, "2401.00001")),
            (await s.get(Paper, "2401.00002")),
        ]
        assert user is not None and task is not None
        assert all(p is not None for p in papers)
        await deliver_email(s, user, task, [p for p in papers if p is not None])

    assert len(MockEmailBackend.sent) == 1
    sent = MockEmailBackend.sent[0]
    assert sent.to == email
    # Subject mentions task name and paper count
    assert "T" in sent.subject
    assert "2" in sent.subject

    async with session_scope() as s:
        rows = (
            await s.scalars(
                select(Delivery).where(
                    Delivery.task_id == task_id,
                    Delivery.channel == "email",
                )
            )
        ).all()
        assert {r.paper_id for r in rows} == {"2401.00001", "2401.00002"}
        assert all(r.user_id == user_id for r in rows)


async def test_deliver_email_no_papers_no_send_no_rows() -> None:
    MockEmailBackend.reset()
    user_id, task_id, _email = await _seed_user_and_task()

    async with session_scope() as s:
        user = await s.get(User, user_id)
        task = await s.get(Task, task_id)
        assert user is not None and task is not None
        await deliver_email(s, user, task, [])

    assert MockEmailBackend.sent == []
    async with session_scope() as s:
        rows = (await s.scalars(select(Delivery).where(Delivery.task_id == task_id))).all()
        assert rows == []


async def test_deliver_email_duplicate_same_paper_fails_unique_constraint() -> None:
    """Calling deliver_email twice with the same paper violates the (task_id,paper_id,channel) uniq."""
    MockEmailBackend.reset()
    user_id, task_id, _email = await _seed_user_and_task()

    async with session_scope() as s:
        user = await s.get(User, user_id)
        task = await s.get(Task, task_id)
        paper = await s.get(Paper, "2401.00001")
        assert user is not None and task is not None and paper is not None
        await deliver_email(s, user, task, [paper])

    # Second delivery of the same paper must raise (IntegrityError) — upstream
    # caller is T13's dedup filter, which guarantees this won't happen in prod.
    import sqlalchemy.exc

    with pytest.raises(sqlalchemy.exc.IntegrityError):
        async with session_scope() as s:
            user = await s.get(User, user_id)
            task = await s.get(Task, task_id)
            paper = await s.get(Paper, "2401.00001")
            assert user is not None and task is not None and paper is not None
            await deliver_email(s, user, task, [paper])
