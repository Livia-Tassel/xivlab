# xivLab Loop Status

**Last updated**: 2026-05-05T18:45:00+08:00
**Last completed Task**: T15 (send_digests Cron Job)
**Next Task**: T16 (RSS Feed Renderer + Endpoint)
**Test suite**: green (127 passed)
**Last commit**: pending — see git log after this iteration

## What's now usable

- `app/jobs/send_digests.py` exposes `run_send_digests()`. The cron iterates all users with `email_verified=True`, computes "now" in each user's tz (`user.tz` via `zoneinfo.ZoneInfo`, falling back to UTC if the string is invalid), and matches their tasks where `enabled=True AND delivery_time == local HH:MM AND "email" in delivery_channels`. For each match it runs T13's `select_papers_for_task` then T14's `deliver_email` (which itself writes the `Delivery` rows). The whole run is wrapped in `cron_run("send_digests")` and reports `digests_sent` (count of non-empty digests delivered) into `cron_runs.job_metadata`.
- The MVP daily digest pipeline is now end-to-end functional minus APScheduler wiring (T22): T11 (embed) → T12 (fetch+vectors) → T13 (filter) → T14 (render+deliver) → T15 (schedule).
- 9 integration tests in `tests/integration/test_send_digests_job.py`: happy path (Asia/Shanghai user, UTC=00:00 → local=08:00 fires), `cron_runs.digests_sent == 1`, skips unverified user, skips disabled task, skips on time mismatch, skips when `delivery_channels=["rss"]`, skips when no candidate papers (no email AND no Delivery rows), invalid-tz fallback to UTC, two-tz simultaneous fire (Asia/Shanghai user with delivery_time=08:00 + UTC user with delivery_time=00:00 both fire at UTC=00:00).

## Plan deviations / fixes

- The plan caught the bad-tz case with bare `except Exception` then assigned `tz = ZoneInfo("UTC")`. Tightened to `except ZoneInfoNotFoundError` (the only thing that *should* go wrong here) and pulled `_UTC = ZoneInfo("UTC")` to module scope so we don't construct it on every loop iteration.
- The plan inlined the local-time conversion in the loop body. Pulled it into `_user_local_hh_mm(now_utc, user_tz) -> str` to make the per-test "what HH:MM does this user see" check verifiable in isolation. (No new direct test of the helper, but the two-tz test exercises both branches.)
- Added 6 tests beyond the plan's hand-wave (it had a single TODO test): unverified user, disabled task, time mismatch, RSS-only, no-papers, invalid tz, two-tz simultaneous. These cover all 4 filter conditions in the user→task→channel pipeline plus the timezone fallback.
- Test fixtures use a `_FrozenDateTime` subclass + `patch("app.jobs.send_digests.datetime", ...)` to control `utcnow()` deterministically. Cleaner than `freezegun` for a single function, no new dep.
- The plan's `await s.execute(select(...)).scalars().all()` pattern was replaced with `await s.scalars(select(...)).all()` — same result, one less hop, matches the style we settled on in T12+T13.

## Open issues / TODOs

- Per-task failures still take down the whole cron run. T15's spec says "if one task explodes, the run fails and is re-runnable" — that's what we have. T22 (APScheduler wiring) or a future hardening pass should add per-task try/except so one bad task doesn't block others.
- `socksio==1.0.0` transitive dep — fine.
- Cookie `secure=False` still hardcoded — T22 / T27.
- `datetime.utcnow()`: 520 warnings (up from 443; cron_log + send_digests are hot paths). Sweep around T15. **Still pending — not done in T15 either; cron_log and the new job both still use utcnow().** Calling this out as the explicit next-cycle cleanup.
- `DEVELOPMENT_GUIDE.md` §11 wording (passlib → bcrypt) still pending.
- Real arXiv API + real OpenAI embeddings still never hit by tests; the send-digest cron mocks `datetime.utcnow` and reads from already-seeded `papers`. First live exercise is the manual smoke test before deploy (T26).
- `delivery_time` is matched as a literal string at the minute resolution. If APScheduler fires at 08:00:30 and `datetime.utcnow().replace(second=0)` lands on 08:00, we match — but if drift pushes us to 08:01, we miss the day's digest entirely. T22 should fire on the 0th second to be safe; if not, we'd need a "missed-window catch-up" pass.

## What's next (T16 high-level reminder)

T16 is the RSS feed renderer + endpoint:
- `app/services/feed_renderer.py` — pure function rendering a list of `Paper` rows into RSS 2.0 XML. One `<item>` per paper with title, link to arxiv abs page, description (abstract truncated), pubDate.
- `app/routers/rss.py` — `GET /rss/{rss_token}` endpoint. Looks up the task by `rss_token`, calls `select_papers_for_task` (or a relaxed variant — RSS shouldn't dedupe via `Delivery` filter since it's pull-based, so likely a new `select_papers_for_rss` or a flag), renders, returns `application/rss+xml`. The T13 pipeline already excludes RSS deliveries from the email-dedup filter, so we just need to NOT write `Delivery(channel='rss')` rows from the endpoint (or write them and accept that the feed self-rotates as new papers arrive).
- Tests: 401-ish on bad token, 200 with valid XML on good token, papers actually appear in `<item>` tags.
