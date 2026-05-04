# xivLab Loop Status

**Last updated**: 2026-05-04T19:55:00+08:00
**Last completed Task**: T03 (Auth — Password Hashing + Register Endpoint)
**Next Task**: T04 (Auth — Login + Sessions + current_user)
**Test suite**: green (13 passed)
**Last commit**: pending — see git log after this iteration

## Notes for next iteration

- **Plan deviation (deliberate, documented):** dropped `passlib[bcrypt]>=1.7` and switched to direct `bcrypt>=4.0`. passlib 1.7.4 reads `bcrypt.__about__.__version__` which was removed in bcrypt 4.1+, and passlib itself is unmaintained. Direct bcrypt is functionally identical (same algorithm, same cost 12) and forward-compatible. `app/services/password.py` now imports `bcrypt` directly. The DEVELOPMENT_GUIDE still says "passlib"; flag for cleanup but it's a one-line wording change, not a code change. **For the next iteration that touches password handling, do not re-introduce passlib.**
- **Plan deviation:** added `email-validator>=2.0` to `pyproject.toml`. Pydantic's `EmailStr` requires it; the plan did not include it. Standard fix.
- **Conftest fixture:** `_reset_db` is autouse, runs before every test. It drops + recreates ORM tables via `Base.metadata`, drops + recreates the `paper_vectors` sqlite-vec virtual table via raw SQL (autogen doesn't track virtual tables), and re-seeds 9 prompt categories. Tests that need pristine alembic-applied state should run against `data/app.db` directly outside of pytest.
- **test_migrations.py:** removed `alembic_version` from expected tables and dropped `test_alembic_version_is_seed_revision` since the autouse reset doesn't apply alembic migrations — it builds the schema directly from `Base.metadata`. The remaining tests (table presence, paper_vectors round-trip) still pass.
- T04 will need:
  - `app/services/session.py` (creating `Session` rows, lookup, expiry)
  - `app/deps.py` (`current_user`, `current_session`, `require_admin`)
  - `app/schemas/auth.py` extension: `LoginRequest`, `SessionInfo`
  - `POST /api/v1/auth/login` (writes a session row, sets HttpOnly cookie)
  - `POST /api/v1/auth/logout` (deletes session row, clears cookie)
  - `GET /api/v1/auth/me` (returns the current user)
  - Tests for happy path login, wrong password 401, /me without cookie 401.

## Bash classifier note

Stable in this iteration.

## Open issues / TODOs surfaced this iteration

- `DEVELOPMENT_GUIDE.md` §11 says "Password hashing: bcrypt via passlib." Code uses direct bcrypt. Quick wording fix later — not blocking.
- `datetime.utcnow` deprecation warning still present (4 warnings now, one per ORM `default=datetime.utcnow` callable that fires during testing). Defer to a single sweep when Module A insertion paths stabilize.
- The seed migration's `description` field (full sentence per category in `0002_seed_categories.py`) is preserved by alembic. The conftest fixture re-seeds with the same description strings — kept in sync by hand. If the migration's seed list changes, update `tests/conftest.py:_SEED_CATEGORIES`.
