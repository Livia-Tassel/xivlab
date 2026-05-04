# xivLab Loop Status

**Last updated**: 2026-05-04T21:35:00+08:00
**Last completed Task**: T08 (Module A — Tasks CRUD API + Quota)
**Next Task**: T09 (Tasks Dashboard UI)
**Test suite**: green (54 passed)
**Last commit**: pending — see git log after this iteration

## What's now usable

- The Task CRUD API is live: `POST /api/v1/tasks`, `GET /api/v1/tasks`, `GET /api/v1/tasks/{id}`, `PATCH`, `DELETE`, plus `POST /{id}/regenerate-rss-token`. All require an authenticated **and email-verified** user (the `require_email_verified` dep).
- Quota: 2 free tasks per user. Third returns 403 with a "limit / buy credits" message. `TaskQuota` row is auto-created on first check and stays at the user-level max (admin can bump in T24).
- `TaskCreate` validators: `arxiv_categories` non-empty list, `delivery_time` matches `HH:MM` 24-hour format (validates 00:00–23:59), `delivery_channels` ⊆ {email, rss} and non-empty, `max_papers_per_day` 1–50, `interest_description` ≤ 1000 chars.
- Per-user isolation verified: a user can't see or operate on another user's tasks (404 across the board).

## Plan deviations / hardenings

- The plan's `delivery_time` regex was `^\d{2}:\d{2}$` which accepts garbage like `99:99`. Tightened to `^(?:[01]\d|2[0-3]):[0-5]\d$`. Added a test (`test_create_rejects_bad_delivery_time`) that exercises this.
- The plan's TaskUpdate had no validators. Mirrored the TaskCreate validators where `is None` short-circuits (PATCH semantics).
- Added 8 tests beyond the plan's 5 (single-task GET, cross-user 404, PATCH, DELETE, unauthenticated 401, empty categories 422, invalid channel 422, bad delivery time 422). Each is a single quick check.
- `list_tasks` orders by `created_at DESC` so the newest task appears first — mirrors how the dashboard UI in T09 will want to render.

## Open issues / TODOs

- The `task_embeddings` row is NOT created on `POST /api/v1/tasks`. The plan deliberately defers that to T11 (embedding service). When `interest_description` is set, the embedding will be backfilled by T11's pipeline. **Don't forget**: T11 must hook into POST and PATCH (re-embed when `interest_description` changes).
- Cookie `secure=False` still hardcoded — T22 / T27.
- `datetime.utcnow()` deprecation: 188 warnings now. Sweep planned around T15 (after the cron pipelines settle).
- `DEVELOPMENT_GUIDE.md` §11 wording (passlib → bcrypt) still pending.
- `/dashboard` still 404s; T09 owns it.

## What's next (T09 high-level reminder)

T09 is the user-facing Tasks dashboard:
- `templates/dashboard/tasks.html` — list of tasks with name, categories, status, edit / delete buttons. Empty state with "Create your first task" CTA.
- `templates/dashboard/task_form.html` — create / edit form. Uses HTMX for inline submission.
- `app/routers/dashboard.py` (or extend `pages.py`) — GET `/dashboard`, GET `/dashboard/tasks/new`, GET `/dashboard/tasks/{id}/edit`, POST handlers for forms.
- All require email-verified user; redirect unverified users to `/verify-pending`.
- Tests: `/dashboard` renders task list, create form posts → 303 redirect, edit pre-fills.
- Plan/spec also has a `/dashboard/prompts` page (T19+) — out of scope for T09.
