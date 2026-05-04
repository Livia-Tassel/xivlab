# xivLab Loop Status

**Last updated**: 2026-05-04T22:00:00+08:00
**Last completed Task**: T09 (Tasks Dashboard UI)
**Next Task**: T10 (arXiv Fetcher Service)
**Test suite**: green (66 passed)
**Last commit**: pending — see git log after this iteration

## What's now usable

- The full Module A user flow (sans the actual paper pipeline) is wired:
  register → verify-email → login → land on `/dashboard` → see "Your tasks (0/2)" empty state → click "+ New task" → fill the form (categories comma-separated, optional keywords/description, time picker, channel checkboxes) → submit → redirected back to `/dashboard` with the task listed → edit / delete / regenerate-RSS-token via inline forms.
- All `/dashboard*` routes redirect: `/login` (no session) or `/verify-pending?email=...` (logged in but unverified). The `_verified_user_or_redirect` helper centralizes this.
- The "+ New task" button is conditionally rendered: hidden when the user is at quota.

## Plan deviations / hardenings

- **Plan was sketchy** about the form post handler — said "delegates to API + redirects" without showing how. I implemented direct service-layer Task creation in pages.py (mirrors the existing pattern from T07 login/register). The CSV-split for `arxiv_categories` and `keywords` is done in the page handler before constructing the Pydantic `TaskCreate`.
- The dashboard's task count display (`tasks|length / max_tasks`) reads `max_tasks` from the user's `TaskQuota` row (not the hardcoded constant the plan suggested). Admin can bump quotas later without a code change.
- Added a confirm prompt on Delete via `onsubmit="return confirm(...)"`. Vanilla JS, no new deps.
- Added a `details/summary` block to surface the RSS feed URL with a copy-friendly `<code>` block + a "Regenerate token" button. The plan only had inline `<code>`.
- Added 12 tests vs the plan's 2 sketches: login/verify-pending redirects, empty state, populated state, form pre-fill, create/update/delete redirects, cross-user 404, quota hides button, validation re-renders form. Each one is a quick request.

## Open issues / TODOs

- The page-form invalid-input test originally tried `name=""` to trigger validation, but FastAPI's `Annotated[str, Form()]` rejects missing/empty strings before the handler runs (returns the default JSON 422). Switched the test to use `arxiv_categories="  "` (whitespace) which goes through the form layer and lands in my Pydantic-level validation. Worth knowing for T19+ when the prompt-create form gets similar tests.
- Cookie `secure=False` still hardcoded — T22 / T27.
- `datetime.utcnow()`: 297 warnings (climbing). Sweep planned around T15.
- `DEVELOPMENT_GUIDE.md` §11 wording (passlib → bcrypt) still pending.
- The dashboard form sends `delivery_channels` as multiple form fields with the same name (HTML checkboxes). FastAPI's `Annotated[list[str] | None, Form()]` parses this. **Don't** add `Field(default_factory=...)` here — that interacts badly with Form parsing.

## What's next (T10 high-level reminder)

T10 is the arXiv API client (no cron yet — T12 wires the cron job):
- `app/services/arxiv_fetcher.py` — `fetch_recent(categories: list[str], since: datetime) -> list[Paper]`. Uses `feedparser` (already installed). Polite rate limit: 3.5s between calls.
- arXiv API URL pattern: `http://export.arxiv.org/api/query?search_query=cat:cs.AI&sortBy=submittedDate&sortOrder=descending&max_results=...`.
- Tests use `tests/fixtures/arxiv_response.xml` (sample fixture) and `unittest.mock.patch` to intercept the HTTP call. Never hit the real API.
- Returns rich tuples or dataclasses, not ORM rows — T12 will own the persistence step.
