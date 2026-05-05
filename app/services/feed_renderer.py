"""Atom feed rendering for per-task RSS endpoints.

Render-only — the router (``app.routers.rss``) handles auth and DB
lookup, then hands a ``Task`` + a list of ``Paper`` rows here. Output
is valid Atom 1.0 XML; ``xml.sax.saxutils.escape`` covers the only
injection vector (paper title, task name, abstract).

We don't use a third-party XML lib — the schema is small, the cost of
hand-rolling it is one ``escape`` call per field, and tests parse the
output with ``ElementTree`` to catch any malformedness.
"""

from datetime import datetime
from xml.sax.saxutils import escape

from app.models import Paper, Task


def _iso_z(dt: datetime | None, fallback: str) -> str:
    """Atom requires RFC3339; we emit naive ISO + 'Z' (assumes UTC throughout)."""
    if dt is None:
        return fallback
    return dt.isoformat() + "Z"


def render_atom(
    task: Task,
    papers: list[Paper],
    *,
    base_url: str,
    user_id: int,
) -> str:
    feed_url = f"{base_url}/rss/{user_id}/{task.id}/feed.xml?token={task.rss_token}"
    updated = datetime.utcnow().isoformat() + "Z"

    entries = []
    for p in papers:
        entry_updated = _iso_z(p.published_at, updated)
        author_names = escape(", ".join(p.authors[:3])) if p.authors else ""
        entries.append(
            "  <entry>\n"
            f"    <id>https://arxiv.org/abs/{p.id}</id>\n"
            f"    <title>{escape(p.title)}</title>\n"
            f"    <updated>{entry_updated}</updated>\n"
            f"    <author><name>{author_names}</name></author>\n"
            f'    <link href="https://arxiv.org/abs/{p.id}"/>\n'
            f'    <summary type="html">{escape(p.abstract[:1000])}</summary>\n'
            f'    <category term="{escape(p.primary_category or "")}"/>\n'
            "  </entry>"
        )
    entries_xml = "\n".join(entries)

    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<feed xmlns="http://www.w3.org/2005/Atom">\n'
        f"  <id>{feed_url}</id>\n"
        f"  <title>{escape(task.name)} · xivLab arXiv 早报</title>\n"
        f"  <updated>{updated}</updated>\n"
        f'  <link href="{feed_url}" rel="self"/>\n'
        f"{entries_xml}\n"
        "</feed>\n"
    )
