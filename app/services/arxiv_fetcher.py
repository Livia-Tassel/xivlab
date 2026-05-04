"""arXiv API fetcher.

Reads from ``http://export.arxiv.org/api/query`` and parses the Atom feed
into ``ArxivPaper`` dataclasses. The parser is the meat; ``fetch_recent``
is a thin async wrapper with retry + rate-limit (per arXiv ToS).

Persistence is NOT this module's job — the digest cron (T12) maps these
dataclasses onto ``Paper`` ORM rows.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

import feedparser
import httpx

ARXIV_API: str = "http://export.arxiv.org/api/query"
RATE_LIMIT_SECONDS: float = 3.5
MAX_RETRIES: int = 3


@dataclass(frozen=True)
class ArxivPaper:
    id: str
    title: str
    abstract: str
    authors: list[str]
    primary_category: str
    all_categories: list[str]
    published_at: datetime | None
    pdf_url: str | None


def _normalize_whitespace(text: str) -> str:
    """Collapse runs of whitespace (incl. newlines) to single spaces. Trim ends."""
    return " ".join(text.split())


def _strip_version(arxiv_id: str) -> str:
    """``2604.12345v2`` → ``2604.12345``. Idempotent if no version suffix."""
    head, sep, _ = arxiv_id.partition("v")
    return head if sep and head else arxiv_id


def parse_feed(xml: str) -> list[ArxivPaper]:
    """Parse an arXiv Atom-format query response into ``ArxivPaper`` items."""
    feed = feedparser.parse(xml)
    out: list[ArxivPaper] = []
    for entry in feed.entries:
        # entry.id is the canonical URL like http://arxiv.org/abs/2604.12345v1
        raw_id = str(entry.id).rsplit("/", 1)[-1]
        clean_id = _strip_version(raw_id)

        tags = cast(list[dict[str, Any]], entry.get("tags") or [])
        cats = [str(t.get("term", "")) for t in tags if t.get("term")]

        primary_dict = cast(dict[str, Any] | None, entry.get("arxiv_primary_category"))
        primary = (
            str(primary_dict["term"])
            if primary_dict and "term" in primary_dict
            else (cats[0] if cats else "")
        )

        pdf_url: str | None = None
        for link in cast(list[dict[str, Any]], entry.get("links") or []):
            if link.get("type") == "application/pdf":
                pdf_url = str(link.get("href"))
                break

        published: datetime | None = None
        parsed = entry.get("published_parsed")
        if parsed is not None:
            # feedparser uses time.struct_time; we only want y/m/d/h/m/s.
            parsed_tuple = cast(tuple[int, ...], parsed)
            year, month, day, hour, minute, second = parsed_tuple[:6]
            published = datetime(year, month, day, hour, minute, second)

        authors: list[str] = []
        for author in cast(list[Any], entry.get("authors") or []):
            name = author.get("name") if isinstance(author, dict) else getattr(author, "name", None)
            if name:
                authors.append(str(name))

        title = _normalize_whitespace(str(entry.get("title", "")))
        abstract = _normalize_whitespace(str(entry.get("summary", "")))

        out.append(
            ArxivPaper(
                id=clean_id,
                title=title,
                abstract=abstract,
                authors=authors,
                primary_category=primary,
                all_categories=cats,
                published_at=published,
                pdf_url=pdf_url,
            )
        )
    return out


async def fetch_recent(categories: list[str], max_results: int = 200) -> list[ArxivPaper]:
    """Fetch recent papers across ``categories`` from arXiv.

    Sorts by submitted date descending. Retries up to 3 times with
    exponential backoff. Sleeps ``RATE_LIMIT_SECONDS`` after success so
    callers that loop over many tasks honor the arXiv rate limit.
    """
    query = " OR ".join(f"cat:{c}" for c in categories)
    params: dict[str, Any] = {
        "search_query": query,
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    last_exc: Exception | None = None
    async with httpx.AsyncClient(timeout=30) as client:
        for attempt in range(MAX_RETRIES):
            try:
                response = await client.get(ARXIV_API, params=params)
                response.raise_for_status()
                papers = parse_feed(response.text)
                await asyncio.sleep(RATE_LIMIT_SECONDS)
                return papers
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt + 1 == MAX_RETRIES:
                    raise
                await asyncio.sleep(2**attempt)
    # Unreachable — the loop either returns or raises.
    if last_exc is not None:
        raise last_exc
    return []
