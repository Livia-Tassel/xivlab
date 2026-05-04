# xivLab Loop Status

**Last updated**: 2026-05-04T22:25:00+08:00
**Last completed Task**: T10 (arXiv Fetcher Service)
**Next Task**: T11 (Embedding Service)
**Test suite**: green (78 passed)
**Last commit**: pending — see git log after this iteration

## What's now usable

- `app/services/arxiv_fetcher.py` exposes `parse_feed(xml) -> list[ArxivPaper]` and `async fetch_recent(categories, max_results=200) -> list[ArxivPaper]`. The fetcher is purely a data-extraction layer — persistence to the `papers` ORM table is T12's job.
- `ArxivPaper` is a frozen dataclass: id, title, abstract, authors, primary_category, all_categories, published_at, pdf_url. All fields normalized (whitespace collapsed, version suffix stripped from arXiv IDs).
- `tests/fixtures/arxiv_response.xml` is a hand-crafted but realistic Atom feed (3 entries, mixed unicode authors, multiple categories, `arxiv:primary_category`, pdf links). Used by 9 parse tests.
- 3 fetch_recent tests use `unittest.mock.patch` over `httpx.AsyncClient.get` and `asyncio.sleep`. They cover: query param construction, retry-then-success, and three-failures-raises.

## Plan deviations / fixes

- **Added `httpx[socks]` to deps** (pyproject.toml). httpx auto-reads `HTTP_PROXY` / `HTTPS_PROXY` from env and tried to use a SOCKS proxy on this machine, blowing up with "socksio not installed". Pinning the `[socks]` extra fixes test envs and is harmless in prod. **Not in the plan.**
- The plan's test asserted `p.id.startswith("")` which is tautological; replaced with concrete checks (`papers[0].id == "2604.12345"`, version-strip verified per-paper).
- The plan's `parse_feed` had several pyright type-correctness rough edges around feedparser's loose stubs (`Optional[Iterable]`, `FeedParserDict | Unknown`). I added explicit `cast()` calls so pyright is silent without `# type: ignore` clutter.
- The plan's title-normalization `entry.title.replace("\n", " ")` only handles newlines; switched to `_normalize_whitespace()` which collapses any run of whitespace. Also applied to abstracts.

## Open issues / TODOs

- `socksio==1.0.0` is now a transitive dep — fine, MIT-licensed, tiny.
- Cookie `secure=False` still hardcoded — T22 / T27.
- `datetime.utcnow()`: 297 warnings. Sweep around T15.
- `DEVELOPMENT_GUIDE.md` §11 wording (passlib → bcrypt) still pending.
- Real arXiv API never hit by tests (per spec); when T12 lands, integration with the live fetcher will be exercised manually before deploy.

## What's next (T11 high-level reminder)

T11 is the embedding service abstraction:
- `app/services/embedding.py` — provider-agnostic interface. `MockBackend` (default in tests/dev) returns deterministic L2-normalized 1536-d vectors keyed off the input string hash. `OpenAIBackend` calls `client.embeddings.create(model=..., input=...)`. Selection via `EMBEDDING_PROVIDER` setting.
- `embed_texts(texts: list[str]) -> list[bytes]` — returns blobs ready for `task_embeddings.embedding` and `paper_vectors`. Float32 little-endian packing (sqlite-vec's expected format).
- Tests: mock backend deterministic across calls, batch handling, blob is 1536*4 = 6144 bytes, OpenAI backend mocked via `patch("openai.AsyncOpenAI")`.
- Don't backfill task_embeddings here — T11 just defines the service. T12+ wire it into the cron pipeline.
