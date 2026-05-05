# xivLab Loop Status

**Last updated**: 2026-05-05T19:10:00+08:00
**Last completed Task**: T16 (RSS/Atom Feed Endpoint)
**Next Task**: T17 (Prompts CRUD API + Spam Guards)
**Test suite**: green (139 passed)
**Last commit**: pending — see git log after this iteration

## What's now usable

- `app/services/feed_renderer.py` exposes `render_atom(task, papers, *, base_url, user_id) -> str`. Pure function: emits valid Atom 1.0 XML with one `<entry>` per paper (id = `https://arxiv.org/abs/<arxiv_id>`, title/abstract entity-escaped via `xml.sax.saxutils.escape`, author = first 3 names joined, link to abs page, summary = abstract truncated to 1000 chars, category = primary_category). Feed-level `<id>`, `<title>`, `<updated>`, and `<link rel="self">` are all populated; the self link includes the token in the query string so feed readers re-poll the right URL.
- `app/routers/rss.py` exposes `GET /rss/{user_id}/{task_id}/feed.xml?token=<rss_token>`. Token mismatch, missing task, or `(user_id, task_id)` belonging to a different owner all return 404 (uniform — never disclose task existence). On success, returns `application/atom+xml` with the rendered feed.
- Feed query: papers joined to `Delivery` rows for that task within the last 30 days, ordered by `Paper.published_at DESC`, capped at 50. Channel is irrelevant (any delivery counts) so RSS subscribers see whatever was sent to email too.
- `app/main.py` registered `rss_router` between `tasks_router` and `pages_router` so the URL prefix is unambiguous (no overlap with `/dashboard`).
- 12 integration tests in `tests/integration/test_rss.py`: 4 token/auth (missing, wrong, mis-routed `user_id`, missing task), 8 happy/structure (200 + correct content-type, one entry per delivery, ordered by published_at DESC, 30-day window cuts stale, task name + self link with token, `& < >` autoescape via `escape` so `ET.fromstring` parses, empty feed valid, 50-entry cap).

## Plan deviations / fixes

- The plan's `render_atom` had `_iso_z` baked into the entry block via a string concat: `f"{p.published_at.isoformat() if p.published_at else updated}Z"`. Bug: when `published_at` was `None`, it appended a stray `Z` to a value that already ended in `Z` (`updated` is built that way). Extracted `_iso_z(dt, fallback) -> str` so the trailing-`Z` rule lives in one place.
- Plan's renderer signature was positional: `render_atom(task, papers, base_url, user_id)`. Made `base_url` and `user_id` keyword-only — too easy to swap them at the call site otherwise.
- Plan's router used `s.execute(select(...)).scalar_one_or_none()`. Switched to `s.scalars(...).one_or_none()` to match the style we settled on in T12+T13+T15. Same semantics.
- Plan's `<category term="{p.primary_category}"/>` didn't escape — `primary_category` is `str | None` and unescaped ampersands would break the XML. Wrapped in `escape(p.primary_category or "")`.
- Plan typed `token: str` as a required path-style param (would 422 on missing). Used `token: str = Query(default="")` so missing/empty token funnels through the same 404 branch as wrong-token (no info leak via different status codes).
- Added 9 tests beyond the plan's 2 sketches: every Atom-feed branch (mis-routed user_id, 30-day cutoff, ordering, 50-cap, escape, empty-state, self-link content) has a dedicated test. Catches regressions when someone edits the renderer.

## Open issues / TODOs

- `socksio==1.0.0` transitive dep — fine.
- Cookie `secure=False` still hardcoded — T22 / T27.
- `datetime.utcnow()`: 775 warnings (up from 520; renderer + router + 12 new tests all touch it). The `T15` callout for a sweep is overdue. **Plan to lift it into T15-or-T16's leftover work after T17 lands**, or do a one-shot global s/utcnow()/now(UTC)/ pass when the count clears 1000.
- `DEVELOPMENT_GUIDE.md` §11 wording (passlib → bcrypt) still pending.
- Real arXiv API + real OpenAI embeddings still never hit by tests; RSS feed just reads the `Delivery` table populated by T14/T15 — no external dep added.
- Atom feed serves any delivered paper for a task regardless of channel. If an RSS-only subscriber wants email-style filtering (e.g., only "high score" papers), we'd need a `Delivery.channel='rss'` write-path or a feed-side filter. Out of scope for MVP.
- The `<feed>` lacks an `<author>` block (only per-entry authors). Acceptable per RFC 4287 since each entry has its own; some readers complain. Add later if users hit it.
- `render_atom` constructs the feed via f-string concatenation, not an XML builder. Cheap, fast, and `escape()` covers the only injection vector — but if we add fields with attribute values, double-check escaping (Atom forbids unescaped `<` `>` `&` `"` `'` in attrs).

## What's next (T17 high-level reminder)

T17 is the Prompts CRUD API + spam guards (PromptHub side of the product, not arXiv digest):
- `app/routers/prompts.py` — POST/GET/PATCH/DELETE on `/api/v1/prompts`. Anonymous-ish: requires login but no email verification, since contributing a prompt is low-trust.
- Spam guards: rate limit per user (e.g., 5/day), basic content checks (length cap, banned-words list, URL count cap), maybe a `pending_review=true` default so admins (T21) can approve before public listing.
- `app/services/prompt_validation.py` — pure-function content checks; tests cover each rule.
- Tests: 401 unauth, 429 over-quota, 201 happy path, 422 on too-long content, prompt vote/copy events tracked.
- T17 is the first endpoint touching `Prompt` / `PromptCategory` / `PromptVote` / `PromptCopyEvent` — exercises ORM models created in T02 that have so far only been schema, not API.
