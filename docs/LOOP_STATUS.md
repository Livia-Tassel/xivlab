# xivLab Loop Status

**Last updated**: 2026-05-04T20:15:00+08:00
**Last completed Task**: T04 (Auth — Login + Sessions + current_user)
**Next Task**: T05 (Auth — Email Service + Verification)
**Test suite**: green (19 passed)
**Last commit**: pending — see git log after this iteration

## Notes for next iteration

- Authentication is now fully wired except email verification: `register` (T03) → `login` issues a `session` cookie and persists a row in `sessions` → `/api/v1/me` resolves the user via the cookie → `logout` deletes the row and clears the cookie.
- `app/deps.py` exposes `current_user`, `require_admin`, `require_email_verified` for downstream routers (T08+ Tasks need `current_user`; admin queue needs `require_admin`).
- Sessions roll: every authenticated request calls `slide_session(...)` which moves `expires_at` and `last_seen_at` forward by `SESSION_LIFETIME` (30 days). When a session DOES expire, `get_session(...)` returns `None` and the cookie holder gets a 401.
- Cookie attributes for login: `httponly=True`, `samesite=lax`, `secure=False`, `max_age=30 days`. **`secure=False` is a TODO** — flip to `True` when `app_env == "prod"` once deploy lands (T22 wires the env-based check, T27 sets the actual prod env). I added a TODO comment in the code.
- httpx `AsyncClient` persists cookies across requests in the same test by default — that's why `register → login → /me` chains in the test work without manual cookie passing.
- Plan said to register the conftest fixture earlier, but the fixture from T03 already covers what T04 needs (autouse `_reset_db`). No conftest changes this iteration.

## Open issues / TODOs surfaced this iteration

- Cookie `secure` flag is hardcoded `False`. **Action item for T22 / T27:** read `settings.app_env` and set `secure=settings.app_env == "prod"` so localhost dev still works while prod requires HTTPS.
- `datetime.utcnow()` deprecation warnings now show 16 occurrences (mostly from session create/get/slide). When the auth surface stabilizes, replace with `datetime.now(UTC)` in a single sweep. **Defer for now**, doesn't block any tests.
- `DEVELOPMENT_GUIDE.md` §11 still says "Password hashing: bcrypt via passlib" — the code uses direct bcrypt (T03 deviation). One-line wording fix.

## What's next (T05 high-level reminder)

- `app/services/email.py` — Resend wrapper + a mock backend (selected via `EMAIL_BACKEND=mock|resend` setting). The mock backend should expose a `sent` list for test inspection.
- `app/services/email_render.py` (or just inline) — Jinja2 templates `templates/emails/verify.html` and `verify.txt`.
- `register` should now ALSO create an `email_verification_tokens` row and dispatch a verification email.
- New endpoint `GET /api/v1/auth/verify-email?token=...` consumes a token (sets `email_verified=True`, marks token `used_at`).
- Tests: register triggers email send, GET verify with valid token → 200 + user.email_verified=True, expired/used token → 410 or 400.
