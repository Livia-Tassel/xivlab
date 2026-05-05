# xivLab Loop Status

**Last updated**: 2026-05-05T17:10:00+08:00
**Last completed Task**: T11 (Embedding Service)
**Next Task**: T12 (arXiv Daily Fetch Cron + cron_runs Logging)
**Test suite**: green (85 passed)
**Last commit**: pending — see git log after this iteration

## What's now usable

- `app/services/embedding.py` — provider-agnostic embedding service. Public API: `EMBEDDING_DIM` (1536), `embed_text(text) -> list[float]`, `to_blob(vec) -> bytes`, `from_blob(blob) -> list[float]`, `MockBackend`, `OpenAIBackend`, `get_backend()`.
- `MockBackend.embed` derives a deterministic L2-normalized 1536-d vector from `sha256(text)`. Identical input → identical output across processes — tests assert exact equality without seeding anything.
- `OpenAIBackend.embed` lazy-imports `openai.AsyncOpenAI` and calls `client.embeddings.create(model=settings.embedding_model, input=text)`. Selection via `settings.embedding_provider` ("mock" default, "openai" for prod).
- `to_blob` / `from_blob` use little-endian float32 packing — sqlite-vec's expected format. 1536 × 4 = 6144 bytes per vector.
- 7 unit tests in `tests/unit/test_embedding.py`: deterministic, distinct inputs, L2-normalized, empty-string safety, blob byte-size, blob roundtrip, OpenAI client mock.

## Plan deviations / fixes

- The plan defined an `EmbeddingBackend` Protocol but never imported it elsewhere. Dropped it — the public `embed_text()` is the consumer-facing API; backend dispatch goes through `get_backend()` returning a class (not an instance), matching the email service's pattern (`type[MockBackend] | type[OpenAIBackend]`).
- The plan had `OpenAIBackend.embed` as an instance method; switched to `@staticmethod` (same as `MockBackend.embed`) so callers can do `OpenAIBackend.embed(text)` without instantiating, matching `email.MockEmailBackend.send` style.
- The plan's `to_blob` used native-endian `struct.pack(f"{n}f", ...)`. Tightened to little-endian explicitly (`<{n}f`) to make the sqlite-vec compatibility contract self-documenting and portable.
- Added 5 tests beyond the plan's 2 (L2-normalization invariant, empty-string safety, blob byte-size = 6144, blob roundtrip identity, OpenAI mock contract). LOOP_STATUS T10 entry called these out as expected; the plan didn't write them down.

## Open issues / TODOs

- `socksio==1.0.0` transitive dep — fine, MIT-licensed, tiny.
- Cookie `secure=False` still hardcoded — T22 / T27.
- `datetime.utcnow()`: 297 warnings. Sweep around T15.
- `DEVELOPMENT_GUIDE.md` §11 wording (passlib → bcrypt) still pending.
- Real arXiv API never hit by tests; T12 lands the cron pipeline and integration with the live fetcher will be exercised manually before deploy.
- Real OpenAI embeddings API never hit by tests; the `OpenAIBackend` test mocks `openai.AsyncOpenAI`. First live exercise will be during T12+ digest-pipeline runs (or whenever the embedding provider is flipped from "mock" to "openai" in dev).

## What's next (T12 high-level reminder)

T12 is the arXiv daily fetch cron + cron_runs logging:
- `app/services/cron_log.py` — small helper to record cron job start/finish/status into the `cron_runs` table.
- `app/jobs/__init__.py`, `app/jobs/fetch_arxiv.py` — the actual job: pull recent papers from `arxiv_fetcher.fetch_recent`, upsert into the `papers` table, generate embeddings via `embedding.embed_text` + `to_blob`, write to `paper_vectors`. Idempotent on `(arxiv_id)` so re-runs don't dup.
- `tests/integration/test_fetch_arxiv_job.py` — full integration test mocking `arxiv_fetcher.fetch_recent` + `embed_text`, asserts papers + embeddings land in the DB and `cron_runs` row is created with the right status.
- T12 is the first job that *uses* T11's blob format end-to-end, so any sqlite-vec packing bugs surface here.
