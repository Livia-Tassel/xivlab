# xivLab Loop Status

**Last updated**: 2026-05-05T17:30:00+08:00
**Last completed Task**: T12 (arXiv Daily Fetch Cron + cron_runs Logging)
**Next Task**: T13 (Digest Filter Pipeline)
**Test suite**: green (89 passed)
**Last commit**: pending — see git log after this iteration

## What's now usable

- `app/services/cron_log.py` exposes `cron_run(job_name)` — an async context manager that records start/end/status into `cron_runs` and yields a mutable `dict[str, Any]` for per-run metrics. Failures re-raise after marking the row `failed` with `error_message` (truncated to 500 chars).
- `app/jobs/__init__.py` is the home of background-job entrypoints called by APScheduler (T22) or backfill scripts. Each module exports a single `run_<name>()` async function.
- `app/jobs/fetch_arxiv.py` exposes `run_fetch_arxiv()`. It pulls from `arxiv_fetcher.fetch_recent(arxiv_category_list, max_results=300)`, upserts into `papers` (idempotent — uses a SELECT-then-add pattern keyed on the arxiv id PK), then walks any `papers` row missing a `paper_vectors` entry, runs `embed_text` + `to_blob`, and inserts the float32 BLOB into the sqlite-vec virtual table. Metrics `fetched` / `new_papers` / `embedded` are written into `cron_runs.job_metadata` for monitoring.
- 4 integration tests in `tests/integration/test_fetch_arxiv_job.py`: happy-path persistence + logging, paper_vectors written, idempotence on re-run (no dupes, second-run metrics zero), and exception path leaves `cron_runs` row with `status='failed'` + `error_message`.

## Plan deviations / fixes

- The plan's upsert used SQLAlchemy's `sqlite_insert.on_conflict_do_nothing(...)` and counted hits via `result.rowcount`. Pyright flags `rowcount` as unknown on `Result[Any]`, and the rowcount semantics for ON CONFLICT DO NOTHING aren't dialect-portable. Replaced with a SELECT-existing-IDs-then-`session.add` pattern: precise count of new rows, no cursor cast, no dialect-specific import. Cron is single-threaded so the read-modify-write window is fine.
- The plan's test mocked `fetch_recent` with `return_value=_fake_papers()` where `_fake_papers` was async — a coroutine can only be awaited once, so re-runs would crash. Switched to `AsyncMock(return_value=[...])` and made `_fake_papers` a plain function returning the list. Idempotence test relies on this.
- The plan's `cron_log.cron_run` accessed `r.ended_at` after `s.get(CronRun, run_id)` without a None-guard; pyright complained. Added `assert r is not None` (cron-runs row was just inserted in the same transaction, so it must exist).
- The plan used `__import__("sqlalchemy").text(...)` inline in the job. Replaced with a module-level `from sqlalchemy import text` import.
- Added 3 tests beyond the plan's 1: paper_vectors written end-to-end, idempotence on second run, failure path. The plan's single happy-path test wouldn't have caught the rowcount/coroutine issues above.

## Open issues / TODOs

- `socksio==1.0.0` transitive dep — fine, MIT-licensed, tiny.
- Cookie `secure=False` still hardcoded — T22 / T27.
- `datetime.utcnow()`: 313 warnings (up from 297; cron_log adds 4 per run + ORM defaults). Sweep around T15.
- `DEVELOPMENT_GUIDE.md` §11 wording (passlib → bcrypt) still pending.
- Real arXiv API never hit by tests; T12 cron mocks `fetch_recent`. First live exercise will be a manual `python -c "import asyncio; from app.jobs.fetch_arxiv import run_fetch_arxiv; asyncio.run(run_fetch_arxiv())"` before deploy.
- `paper_vectors` insert uses raw `text()` because sqlite-vec virtual tables aren't ORM-mapped. Acceptable per the migration's design.

## What's next (T13 high-level reminder)

T13 is the digest filter pipeline:
- `app/services/digest.py` — pure functions over already-fetched/embedded papers. Inputs: a `Task` (with arxiv_categories, keywords, max_papers_per_day) and the date window. Outputs: a ranked, deduplicated list of `Paper` rows with similarity scores attached.
- Filter stages: (1) category filter (arxiv_categories overlap with paper.all_categories), (2) keyword OR-match against title/abstract, (3) embedding similarity vs the task's embedding (stored in `task_embeddings.embedding`), (4) cap at `max_papers_per_day`.
- `tests/unit/test_digest_filter.py` — covers each stage and the composed pipeline. No DB required for the pure functions (build Paper-shaped objects in memory) but a DB-backed integration test will exercise `paper_vectors` similarity.
- T13 is the first consumer of T11's blob format and T12's `paper_vectors` rows; bugs in either surface here.
