"""Daily arXiv fetch + embed cron job.

Pulls recent papers from configured arXiv categories, upserts them into
the ``papers`` table (idempotent via ON CONFLICT DO NOTHING on arxiv id),
and embeds any paper that doesn't yet have a ``paper_vectors`` row.

The whole run is wrapped in :func:`app.services.cron_log.cron_run` so a
``cron_runs`` row records start/end/status and per-run metrics
(``fetched`` / ``new_papers`` / ``embedded``).
"""

from sqlalchemy import select, text

from app.config import get_settings
from app.db import session_scope
from app.models import Paper
from app.services.arxiv_fetcher import fetch_recent
from app.services.cron_log import cron_run
from app.services.embedding import embed_text, to_blob


async def run_fetch_arxiv() -> None:
    async with cron_run("fetch_arxiv") as meta:
        cats = get_settings().arxiv_category_list
        papers = await fetch_recent(cats, max_results=300)
        meta["fetched"] = len(papers)

        async with session_scope() as s:
            existing_ids: set[str] = set(
                (
                    await s.scalars(select(Paper.id).where(Paper.id.in_([p.id for p in papers])))
                ).all()
            )
            new_papers = [p for p in papers if p.id not in existing_ids]
            for p in new_papers:
                s.add(
                    Paper(
                        id=p.id,
                        title=p.title,
                        abstract=p.abstract,
                        authors=p.authors,
                        primary_category=p.primary_category,
                        all_categories=p.all_categories,
                        published_at=p.published_at,
                        pdf_url=p.pdf_url,
                    )
                )
            await s.commit()
        meta["new_papers"] = len(new_papers)

        embedded = 0
        async with session_scope() as s:
            unvec_stmt = text(
                "SELECT p.id, p.title, p.abstract FROM papers p "
                "LEFT JOIN paper_vectors pv ON pv.paper_id = p.id "
                "WHERE pv.paper_id IS NULL LIMIT 300"
            )
            rows = (await s.execute(unvec_stmt)).all()
            insert_vec = text("INSERT INTO paper_vectors(paper_id, embedding) VALUES (:pid, :emb)")
            for pid, title, abstract in rows:
                vec = await embed_text(f"{title}\n\n{abstract}")
                blob = to_blob(vec)
                await s.execute(insert_vec, {"pid": pid, "emb": blob})
                embedded += 1
            await s.commit()
        meta["embedded"] = embedded
