from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.services.arxiv_fetcher import ArxivPaper, fetch_recent, parse_feed

_FIXTURE = Path(__file__).parent.parent / "fixtures" / "arxiv_response.xml"


def test_parse_fixture_returns_three_papers() -> None:
    papers = parse_feed(_FIXTURE.read_text(encoding="utf-8"))
    assert len(papers) == 3
    assert all(isinstance(p, ArxivPaper) for p in papers)


def test_parse_extracts_arxiv_id_without_version() -> None:
    papers = parse_feed(_FIXTURE.read_text(encoding="utf-8"))
    assert papers[0].id == "2604.12345"
    assert papers[1].id == "2604.67890"  # was "2604.67890v2" in feed
    assert papers[2].id == "2604.99999"


def test_parse_normalizes_title_whitespace() -> None:
    papers = parse_feed(_FIXTURE.read_text(encoding="utf-8"))
    # Title in fixture has a literal newline + indent; parser must collapse to single space.
    assert "\n" not in papers[0].title
    assert "  " not in papers[0].title.replace("  ", "X")  # no double-space artifacts
    assert papers[0].title.startswith("Self-Reflective Multi-Agent")


def test_parse_extracts_authors_including_unicode() -> None:
    papers = parse_feed(_FIXTURE.read_text(encoding="utf-8"))
    assert papers[0].authors == ["Alice Chen", "Bob Müller", "张三"]
    assert papers[1].authors == ["Carol Singh"]


def test_parse_extracts_categories_and_primary() -> None:
    papers = parse_feed(_FIXTURE.read_text(encoding="utf-8"))
    assert papers[0].primary_category == "cs.AI"
    assert set(papers[0].all_categories) == {"cs.AI", "cs.CL", "cs.LG"}
    assert papers[1].primary_category == "cs.CV"
    assert papers[2].primary_category == "stat.ML"


def test_parse_extracts_published_at() -> None:
    papers = parse_feed(_FIXTURE.read_text(encoding="utf-8"))
    assert papers[0].published_at == datetime(2026, 5, 4, 8, 30, 0)


def test_parse_extracts_pdf_url() -> None:
    papers = parse_feed(_FIXTURE.read_text(encoding="utf-8"))
    assert papers[0].pdf_url == "http://arxiv.org/pdf/2604.12345v1"


def test_parse_strips_abstract_whitespace() -> None:
    papers = parse_feed(_FIXTURE.read_text(encoding="utf-8"))
    abstract = papers[0].abstract
    assert abstract.startswith("We propose SRM-Agent")
    assert abstract.endswith("baselines.")


def test_parse_empty_feed_returns_empty_list() -> None:
    empty_feed = (
        '<?xml version="1.0" encoding="UTF-8"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>'
    )
    assert parse_feed(empty_feed) == []


async def test_fetch_recent_builds_query_and_parses() -> None:
    """Mock httpx.AsyncClient.get to return our fixture; verify parse runs."""
    fixture_text = _FIXTURE.read_text(encoding="utf-8")

    class _MockResponse:
        text = fixture_text

        def raise_for_status(self) -> None:
            return None

    captured: dict[str, object] = {}

    async def _fake_get(self: object, url: str, params: dict[str, object]) -> _MockResponse:
        captured["url"] = url
        captured["params"] = params
        return _MockResponse()

    # Bypass the rate-limit sleep so the test stays fast.
    with (
        patch("app.services.arxiv_fetcher.httpx.AsyncClient.get", new=_fake_get),
        patch("app.services.arxiv_fetcher.asyncio.sleep", new=AsyncMock()),
    ):
        papers = await fetch_recent(["cs.AI", "cs.LG"], max_results=3)

    assert len(papers) == 3
    assert captured["url"].endswith("/api/query")  # type: ignore[union-attr]
    params = captured["params"]
    assert isinstance(params, dict)
    assert params["search_query"] == "cat:cs.AI OR cat:cs.LG"
    assert params["max_results"] == 3
    assert params["sortBy"] == "submittedDate"
    assert params["sortOrder"] == "descending"


async def test_fetch_recent_retries_on_transient_failure() -> None:
    """First two calls raise, third succeeds — should still return parsed papers."""
    import httpx

    fixture_text = _FIXTURE.read_text(encoding="utf-8")

    class _MockResponse:
        text = fixture_text

        def raise_for_status(self) -> None:
            return None

    call_count = {"n": 0}

    async def _flaky_get(self: object, url: str, params: dict[str, object]) -> _MockResponse:
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise httpx.ConnectError("simulated transient failure")
        return _MockResponse()

    with (
        patch("app.services.arxiv_fetcher.httpx.AsyncClient.get", new=_flaky_get),
        patch("app.services.arxiv_fetcher.asyncio.sleep", new=AsyncMock()),
    ):
        papers = await fetch_recent(["cs.AI"])

    assert call_count["n"] == 3
    assert len(papers) == 3


async def test_fetch_recent_raises_after_three_failures() -> None:
    import httpx

    async def _always_fail(self: object, url: str, params: dict[str, object]) -> object:
        raise httpx.ConnectError("perma fail")

    with (
        patch("app.services.arxiv_fetcher.httpx.AsyncClient.get", new=_always_fail),
        patch("app.services.arxiv_fetcher.asyncio.sleep", new=AsyncMock()),
    ):
        try:
            await fetch_recent(["cs.AI"])
        except httpx.ConnectError:
            return
        raise AssertionError("expected ConnectError after retries exhausted")
