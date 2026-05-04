# xivLab Loop Status

**Last updated**: 2026-05-04T20:50:00+08:00
**Last completed Task**: T06 (Auth — Password Reset)
**Next Task**: T07 (Frontend Foundation — Base Templates + Auth Pages)
**Test suite**: green (32 passed)
**Last commit**: pending — see git log after this iteration

## Notes for next iteration

- The full auth surface is now stood up: register / verify-email / login / logout / me / forgot-password / reset-password. All endpoints under `/api/v1/auth/`.
- `forgot-password`: anti-enumeration design — always returns 200, never reveals whether the email exists. The DB write + email send happens INSIDE the `session_scope` only when the user exists; the email send is hoisted OUTSIDE the session scope (after the commit) so we don't hold the DB connection during the network call.
- `reset-password`: validates token (existence, not used, not expired), bcrypt-hashes the new password, marks token `used_at`. One-shot — second use returns 404.
- 6 new password-reset integration tests added (happy-path + invalid-token + one-shot + short-password validation + anti-enumeration).
- Phase 1 (Auth, T03–T06 in our numbering — actually T03–T06 in the plan map to T03 register, T04 login/logout/me, T05 verify-email, T06 password-reset) is **done**.

## Plan deviations / fixes this iteration

- Added `test_reset_password_invalid_token_404`, `test_reset_password_token_is_one_shot`, `test_reset_password_short_password_422` beyond the plan's 3 tests. They cover invariants the plan implies but doesn't directly test. Cheap to add, raises confidence in the one-shot semantics that mirror the verify-email flow.
- Email send for `forgot-password` is hoisted out of the DB transaction (vs the plan's inline `await send_email(...)` inside `session_scope`). A long network call shouldn't hold a SQLite write lock on a 2 vCPU box.

## Open issues / TODOs

- Cookie `secure=False` — pending T22 / T27.
- `datetime.utcnow()` deprecation: 54 warnings now. Defer to a single sweep after Module A inserts stabilize (probably between T11 and T15).
- `DEVELOPMENT_GUIDE.md` §11 wording fix (passlib → bcrypt) pending.

## What's next (T07 high-level reminder)

T07 is the frontend foundation:
- `templates/base.html` — Tailwind CDN + HTMX, base layout with header/footer
- `templates/auth/{login,register,verify,forgot,reset}.html` — server-rendered HTML pages backed by a `pages` router
- `app/routers/pages.py` — GET `/`, `/login`, `/register`, etc. — these render Jinja2 templates and let HTMX handle the form posts (the underlying API endpoints are already done in T03–T06)
- Wire Jinja2Templates into `app.main`
- The forms POST to JSON endpoints we already built; HTMX response handling redirects on success.
- Tests: smoke-check that `/login`, `/register` return 200 with HTML content-type. Don't go deeper than that — visual / browser testing isn't in the test budget.
