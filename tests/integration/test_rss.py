"""Integration tests for the per-task Atom feed endpoint.

Endpoint shape: ``GET /rss/{user_id}/{task_id}/feed.xml?token=<rss_token>``.

Token check is the only auth — no session cookie required, since feed
readers don't carry them. Requests with a missing, wrong, or
mis-routed (right token, wrong user/task pair) token must return 404
to avoid disclosing task existence.

Body content: ``application/atom+xml`` containing one ``<entry>`` per
delivered paper, ordered by ``published_at`` desc, limited to the most
recent 30 days of deliveries (capped at 50 entries).
"""

import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select

from app.db import session_scope
from app.models import Delivery, Paper, Task, User

ATOM_NS = "{http://www.w3.org/2005/Atom}"


def _paper(pid: str, *, published_at: datetime | None = None, title: str | None = None) -> Paper:
    return Paper(
        id=pid,
        title=title or f"Title {pid}",
        abstract=f"Abstract for {pid}." * 20,
        authors=["Alice", "Bob"],
        primary_category="cs.AI",
        all_categories=["cs.AI"],
        published_at=published_at or (datetime.utcnow() - timedelta(hours=2)),
        pdf_url=None,
    )


async def _seed_user_with_task(rss_token: str = "rt-" + "a" * 37) -> tuple[int, int, str]:
    async with session_scope() as s:
        u = User(email="rss@x.dev", password_hash="x", email_verified=True)
        s.add(u)
        await s.commit()
        t = Task(
            user_id=u.id,
            name="My Feed",
            arxiv_categories=["cs.AI"],
            keywords=None,
            min_keyword_match=1,
            max_papers_per_day=10,
            delivery_time="08:00",
            delivery_channels=["email"],
            rss_token=rss_token,
            enabled=True,
        )
        s.add(t)
        await s.commit()
        return u.id, t.id, rss_token


# --- token auth -----------------------------------------------------------


async def test_feed_404_when_token_missing(client: AsyncClient) -> None:
    user_id, task_id, _ = await _seed_user_with_task()
    r = await client.get(f"/rss/{user_id}/{task_id}/feed.xml")
    assert r.status_code == 404


async def test_feed_404_when_token_wrong(client: AsyncClient) -> None:
    user_id, task_id, _ = await _seed_user_with_task()
    r = await client.get(
        f"/rss/{user_id}/{task_id}/feed.xml",
        params={"token": "wrong-token-" + "x" * 30},
    )
    assert r.status_code == 404


async def test_feed_404_when_user_id_does_not_match_task_owner(
    client: AsyncClient,
) -> None:
    """Right token + task_id, but user_id in path belongs to someone else."""
    _owner_id, task_id, token = await _seed_user_with_task()
    async with session_scope() as s:
        other = User(email="other@x.dev", password_hash="x", email_verified=True)
        s.add(other)
        await s.commit()
        other_id = other.id

    r = await client.get(
        f"/rss/{other_id}/{task_id}/feed.xml",
        params={"token": token},
    )
    assert r.status_code == 404


async def test_feed_404_when_task_does_not_exist(client: AsyncClient) -> None:
    user_id, _task_id, token = await _seed_user_with_task()
    r = await client.get(
        f"/rss/{user_id}/99999/feed.xml",
        params={"token": token},
    )
    assert r.status_code == 404


# --- happy path -----------------------------------------------------------


async def test_feed_200_returns_atom_xml_with_correct_content_type(
    client: AsyncClient,
) -> None:
    user_id, task_id, token = await _seed_user_with_task()
    r = await client.get(
        f"/rss/{user_id}/{task_id}/feed.xml",
        params={"token": token},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/atom+xml")


async def test_feed_contains_one_entry_per_delivered_paper(client: AsyncClient) -> None:
    user_id, task_id, token = await _seed_user_with_task()
    async with session_scope() as s:
        s.add(_paper("2401.00001"))
        s.add(_paper("2401.00002"))
        await s.commit()
        s.add(
            Delivery(
                user_id=user_id,
                task_id=task_id,
                paper_id="2401.00001",
                channel="email",
            )
        )
        s.add(
            Delivery(
                user_id=user_id,
                task_id=task_id,
                paper_id="2401.00002",
                channel="email",
            )
        )
        await s.commit()

    r = await client.get(
        f"/rss/{user_id}/{task_id}/feed.xml",
        params={"token": token},
    )
    assert r.status_code == 200

    root = ET.fromstring(r.text)
    entries = root.findall(f"{ATOM_NS}entry")
    assert len(entries) == 2

    # Each entry has the paper's arxiv id in <id> and a link to arxiv.org/abs/<id>.
    ids = {e.findtext(f"{ATOM_NS}id") for e in entries}
    assert ids == {
        "https://arxiv.org/abs/2401.00001",
        "https://arxiv.org/abs/2401.00002",
    }


async def test_feed_orders_entries_by_published_at_desc(client: AsyncClient) -> None:
    user_id, task_id, token = await _seed_user_with_task()
    now = datetime.utcnow()
    async with session_scope() as s:
        s.add(_paper("p-old", published_at=now - timedelta(days=2)))
        s.add(_paper("p-mid", published_at=now - timedelta(hours=12)))
        s.add(_paper("p-new", published_at=now - timedelta(hours=1)))
        await s.commit()
        for pid in ("p-old", "p-mid", "p-new"):
            s.add(
                Delivery(
                    user_id=user_id,
                    task_id=task_id,
                    paper_id=pid,
                    channel="email",
                )
            )
        await s.commit()

    r = await client.get(
        f"/rss/{user_id}/{task_id}/feed.xml",
        params={"token": token},
    )
    root = ET.fromstring(r.text)
    ids = [e.findtext(f"{ATOM_NS}id") for e in root.findall(f"{ATOM_NS}entry")]
    assert ids == [
        "https://arxiv.org/abs/p-new",
        "https://arxiv.org/abs/p-mid",
        "https://arxiv.org/abs/p-old",
    ]


async def test_feed_excludes_deliveries_older_than_30_days(client: AsyncClient) -> None:
    user_id, task_id, token = await _seed_user_with_task()
    async with session_scope() as s:
        s.add(_paper("p-fresh"))
        s.add(_paper("p-stale"))
        await s.commit()
        # Backdate one delivery beyond the 30-day window.
        d_stale = Delivery(
            user_id=user_id,
            task_id=task_id,
            paper_id="p-stale",
            channel="email",
            delivered_at=datetime.utcnow() - timedelta(days=45),
        )
        d_fresh = Delivery(
            user_id=user_id,
            task_id=task_id,
            paper_id="p-fresh",
            channel="email",
        )
        s.add_all([d_stale, d_fresh])
        await s.commit()

    r = await client.get(
        f"/rss/{user_id}/{task_id}/feed.xml",
        params={"token": token},
    )
    root = ET.fromstring(r.text)
    ids = {e.findtext(f"{ATOM_NS}id") for e in root.findall(f"{ATOM_NS}entry")}
    assert ids == {"https://arxiv.org/abs/p-fresh"}


async def test_feed_includes_task_name_and_self_link(client: AsyncClient) -> None:
    user_id, task_id, token = await _seed_user_with_task()
    r = await client.get(
        f"/rss/{user_id}/{task_id}/feed.xml",
        params={"token": token},
    )
    root = ET.fromstring(r.text)
    title = root.findtext(f"{ATOM_NS}title") or ""
    assert "My Feed" in title

    # <link rel="self" href="..."> with the token in the URL.
    self_links = [
        link.get("href") for link in root.findall(f"{ATOM_NS}link") if link.get("rel") == "self"
    ]
    assert len(self_links) == 1
    assert token in (self_links[0] or "")
    assert f"/rss/{user_id}/{task_id}/feed.xml" in (self_links[0] or "")


async def test_feed_escapes_unsafe_chars_in_title(client: AsyncClient) -> None:
    """Titles containing & < > must be entity-escaped, not injected raw."""
    user_id, task_id, token = await _seed_user_with_task()
    async with session_scope() as s:
        s.add(_paper("p-unsafe", title="A & B <hack>"))
        await s.commit()
        s.add(
            Delivery(
                user_id=user_id,
                task_id=task_id,
                paper_id="p-unsafe",
                channel="email",
            )
        )
        await s.commit()

    r = await client.get(
        f"/rss/{user_id}/{task_id}/feed.xml",
        params={"token": token},
    )
    # Body must parse — that alone proves escaping worked, since "<hack>"
    # raw would break the XML.
    root = ET.fromstring(r.text)
    titles = [e.findtext(f"{ATOM_NS}title") for e in root.findall(f"{ATOM_NS}entry")]
    assert "A & B <hack>" in titles  # ET un-escapes for us


async def test_feed_with_no_deliveries_returns_valid_empty_feed(
    client: AsyncClient,
) -> None:
    user_id, task_id, token = await _seed_user_with_task()
    r = await client.get(
        f"/rss/{user_id}/{task_id}/feed.xml",
        params={"token": token},
    )
    assert r.status_code == 200
    root = ET.fromstring(r.text)
    assert root.findall(f"{ATOM_NS}entry") == []
    # Verify the task seed was actually present (not silently filtered out).
    async with session_scope() as s:
        t = (await s.scalars(select(Task).where(Task.id == task_id))).one()
        assert t.name == "My Feed"


async def test_feed_caps_at_50_entries(client: AsyncClient) -> None:
    user_id, task_id, token = await _seed_user_with_task()
    async with session_scope() as s:
        for i in range(60):
            s.add(_paper(f"p{i:03d}"))
        await s.commit()
        for i in range(60):
            s.add(
                Delivery(
                    user_id=user_id,
                    task_id=task_id,
                    paper_id=f"p{i:03d}",
                    channel="email",
                )
            )
        await s.commit()

    r = await client.get(
        f"/rss/{user_id}/{task_id}/feed.xml",
        params={"token": token},
    )
    root = ET.fromstring(r.text)
    assert len(root.findall(f"{ATOM_NS}entry")) == 50
