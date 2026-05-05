# xivLab Loop Status

**Last updated**: 2026-05-05T17:55:00+08:00
**Last completed Task**: T13 (Digest Filter Pipeline)
**Next Task**: T14 (Email Rendering + Send Digest)
**Test suite**: green (104 passed)
**Last commit**: pending — see git log after this iteration

## What's now usable

- `app/services/digest.py` — pure-and-DB-mixed digest pipeline. Public API: `select_papers_for_task(s, task) -> list[Paper]`, plus building blocks `candidates_for_task`, `keyword_match`, `cosine`, `get_or_compute_task_embedding`, `get_paper_embedding`.
- Pipeline stages (in order): (1) primary_category ∈ task.arxiv_categories AND published within `since_hours` (default 36), (2) keyword filter against title+abstract (case-insensitive substring, requires ≥ `task.min_keyword_match` hits), (3) semantic rerank by descending `cosine(task_vec, paper_vec)` if `task.interest_description` is set, (4) drop already-delivered (channel='email' only — RSS deliveries are pull-based and don't dedup), (5) cap at `task.max_papers_per_day`.
- Task embedding cache: `task_embeddings` keyed by `task_id`, invalidated when `source_text != task.interest_description`. Both fresh and cached returns go through `from_blob(to_blob(vec))` so callers get bit-identical float32-precision results regardless of cache state.
- 15 tests in `tests/unit/test_digest_filter.py`: 5 pure (keyword case-insensitivity, no-keywords zero, title-or-abstract search, cosine orthogonal, cosine identity); 10 DB-backed (category filter, recency window, min_keyword_match, semantic rerank order, email-delivery dedup, RSS delivery NOT deduped, max_papers cap, task embedding cache, cache invalidation, None-description path).

## Plan deviations / fixes

- The plan returned the freshly-computed `vec` directly on cache miss, but cached returns went through `from_blob(blob)`. Float64 vs float32 mismatch broke the cache-equality test. Fixed: always return `from_blob(to_blob(vec))` so both branches yield identical float32-precision vectors.
- The plan called the dot-product helper `cosine`, which is technically correct only for unit-length inputs. Kept the name for API compatibility but documented the precondition (MockBackend and OpenAI's text-embedding-3-small both return L2-normalized vectors).
- The plan's tests were stub one-liners ("Full test bodies in plan execution; key behaviors..."). Wrote them out properly: 15 tests instead of 4, covering each stage plus 3 invariants the plan glossed over (cache invalidation on text change, None-description short-circuit, RSS-doesn't-dedup-email).
- The plan used `__import__("sqlalchemy").text(...)` inline. Replaced with module-level imports (already done in T12, applied here too).
- The semantic-rerank test pre-seeds `task_embeddings` and `paper_vectors` with hand-crafted basis-vector blobs (`[1,0,...]` vs `[0,1,...]`) so the expected ordering is exact and independent of MockBackend's hash-derived noise. The plan's stub assumed real OpenAI embeddings would produce a meaningful order; that's brittle even before considering test-determinism.

## Open issues / TODOs

- `socksio==1.0.0` transitive dep — fine.
- Cookie `secure=False` still hardcoded — T22 / T27.
- `datetime.utcnow()`: 424 warnings (up from 313; digest.py adds two more sites). Sweep around T15.
- `DEVELOPMENT_GUIDE.md` §11 wording (passlib → bcrypt) still pending.
- Real arXiv API + real OpenAI embeddings still never hit by tests; first live exercise comes during the T14/T15 send-digest cron runs.
- Category filter is `primary_category.in_(...)`. Cross-listed papers (where the user's category is in `all_categories` but not primary) are excluded. Could broaden to `JSON_EXTRACT(all_categories) overlaps task.arxiv_categories` later, but that's a UX call — the current behavior is "stricter, less noise".
- The digest pipeline calls `get_paper_embedding` once per candidate (one SELECT each). Acceptable for daily cron with ≤ ~300 papers/day, but for a hot path we'd batch-fetch with a single `WHERE paper_id IN (...)` query. Not a problem at this scale.

## What's next (T14 high-level reminder)

T14 is email rendering + send-digest:
- `app/services/digest_email.py` (or similar) — render an HTML/text email containing the top-N papers for a task. Jinja templates under `app/templates/emails/`.
- Calls `select_papers_for_task` for each enabled task, renders, sends via the existing `email.send_email` (mock/Resend), then writes a `Delivery` row per paper (channel='email') so the next run dedupes.
- Tests: render snapshot (HTML & text both have title/abstract/link), end-to-end mock-send with the digest pipeline producing N papers and N+1 Delivery rows being created.
- T14 is the first integration of T11 (embeddings) → T12 (paper_vectors) → T13 (digest) → email; bugs in any earlier layer surface here.
