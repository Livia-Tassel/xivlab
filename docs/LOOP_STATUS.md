# xivLab Loop Status

**Last updated**: 2026-05-04T21:15:00+08:00
**Last completed Task**: T07 (Frontend Foundation — Base Templates + Auth Pages)
**Next Task**: T08 (Module A — Tasks CRUD API + Quota)
**Test suite**: green (41 passed)
**Last commit**: pending — see git log after this iteration

## What's now usable end-to-end

- The HTML auth flow is wired: visit `/register` → submit form → redirected to `/verify-pending?email=…` → click link in email → `/verify-email/{token}` flips `email_verified=True` → `/login` → cookie set, redirected to `/dashboard` (a 404 for now — T08/T09 territory) → `/forgot-password` and `/reset-password/{token}` work the same way. All forms post to dedicated `pages.py` handlers (no client-side JS required).
- `/static` is mounted but empty (placeholder `static/.gitkeep`). Tailwind + HTMX + Alpine load via CDN in `templates/base.html`.

## Plan deviations / notes

- **Pages handlers call services directly** instead of re-invoking the API endpoints (the plan suggested `from app.routers.auth import login as api_login` + `redirect.raw_headers.extend(response.raw_headers)`). The plan's pattern works but cookie-header copying through Starlette internals is fragile and the duplicated logic is small. My version uses `RedirectResponse + set_cookie` which is idiomatic Starlette.
- **Verify-email link is a GET** (the API endpoint stays POST for programmatic use). Real email clients don't POST — so `/verify-email/{token}` on the pages router consumes the token on GET and renders `auth/verify_result.html`. The JSON `POST /api/v1/auth/verify-email/{token}` is still there for SPA / API clients.
- **Added `templates/auth/verify_result.html`** beyond the plan's 5 templates — it's the landing page after the user clicks the verify link.
- Deprecation warnings still climbing (62 now). Will sweep in one go after Module A inserts settle.

## Open issues / TODOs

- `/dashboard` is referenced from `/login` redirect and from `base.html` nav, but no route serves it yet. T09 creates it. Until then, post-login users see a 404. **Action item: T09 must land before any user-facing demo.**
- Cookie `secure=False` still hardcoded. T22 / T27 owner.
- `DEVELOPMENT_GUIDE.md` §11 wording (passlib → bcrypt) still pending.

## What's next (T08 high-level reminder)

T08 is the start of Module A (arXiv 早报):
- `app/schemas/tasks.py` — TaskCreate / TaskUpdate / TaskOut
- `app/services/quota.py` — quota check (default 2 tasks per user, configurable via `TaskQuota.max_tasks`)
- `app/routers/tasks.py` — CRUD: POST/GET/list/PATCH/DELETE under `/api/v1/tasks/*`
- All endpoints require `current_user` + `require_email_verified` (verified-only invariant from spec §6.1)
- POST creates `rss_token = secrets.token_urlsafe(32)` automatically
- POST also embeds the `interest_description` to populate `task_embeddings.embedding` — but T11 owns the embedding pipeline. T08 should leave the embedding row blank or use a `MockBackend` returning zero-vectors; T11 will rewire.
- Tests: happy CRUD; quota blocks third task; unverified user can't create.
