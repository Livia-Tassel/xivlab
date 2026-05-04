# xivLab Loop Status

**Last updated**: 2026-05-04T20:35:00+08:00
**Last completed Task**: T05 (Auth — Email Service + Verification)
**Next Task**: T06 (Auth — Password Reset)
**Test suite**: green (26 passed)
**Last commit**: pending — see git log after this iteration

## Notes for next iteration

- `app/services/email.py` exposes `send_email(to, subject, html, text)` with two backends:
  - `MockEmailBackend` (default in tests/dev) — records each call on the class-level `sent: list[SentEmail]`. Tests inspect this list.
  - `ResendBackend` — uses `resend.Emails.send_async` (the SDK's native async surface, not `asyncio.to_thread` over the sync API as the plan suggested). Imports `resend` lazily inside the method so test envs without an API key don't have to install it.
- Registration flow now: insert user → flush → insert `EmailVerificationToken` (48h expiry) → commit → refresh user → build `UserPublic` → release session → send email → return UserPublic.
- The verify URL in the email is `{settings.app_base_url}/verify-email/{token}` — that's a frontend route. The email's link points users to a future T07 page that POSTs to `/api/v1/auth/verify-email/{token}`.
- `POST /api/v1/auth/verify-email/{token}` returns 200 + `{"ok": True}` on success, 404 on missing/expired/used token. Tokens are one-shot (`used_at` is stamped on consumption).
- The autouse `_reset_db` conftest fixture now also calls `MockEmailBackend.reset()` so emails don't bleed between tests.

## Plan deviations (deliberate, documented)

- Switched `ResendBackend` to use the SDK's native `Emails.send_async` instead of the plan's `asyncio.to_thread(Emails.send, ...)`. The native async path is cleaner and the plan's pattern would still work; this is purely a quality bump.
- Typed the Resend params dict as `resend.Emails.SendParams` (which the SDK exposes) so pyright's strict TypedDict check passes without `# type: ignore`.

## Open issues / TODOs

- Cookie `secure=False` still hardcoded in login. **T22 / T27 owner**: read `settings.app_env` and flip to `secure=settings.app_env == "prod"`.
- `datetime.utcnow()` deprecation warnings now at 39 (every register/login/verify path triggers ORM defaults). Defer the sweep — purely cosmetic.
- `DEVELOPMENT_GUIDE.md` §11 still says "passlib" — pending one-line edit.

## What's next (T06 high-level reminder)

- `app/schemas/auth.py` — add `ForgotPasswordRequest`, `ResetPasswordRequest`.
- New endpoints under `/api/v1/auth/`:
  - `POST /forgot-password` — always returns 200 (anti-enumeration). Internally: if email exists, create `PasswordResetToken` (48h), email a reset link.
  - `POST /reset-password` — body `{ token, new_password }`. Validates token, hashes new password, marks token used.
- Tests: forgot-password is idempotent on missing email; reset-password rejects invalid/expired tokens; old password no longer works after reset.
- Email rendering can stay inline (no Jinja2 templates yet — that's T07's job).
