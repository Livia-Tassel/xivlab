# xivLab Development Guide

> **Audience**: Any agent (or human) writing code in this repo.
> **Authority**: This file's conventions override defaults. The implementation plan and design spec describe **what** to build; this file describes **how** to build it.

---

## 1. Languages & Versions

- Python **3.12+** (required for type syntax `int | None`, Pydantic v2)
- Package manager: `uv` (NEVER use pip/poetry/pipenv)
- All shell commands assume `uv run <cmd>` prefix when invoking project tools

---

## 2. Code Style

### 2.1 Formatting & linting

- **`ruff format`** is the formatter. Run `uv run ruff format` before any commit.
- **`ruff check --fix`** is the linter. Settings in `ruff.toml`. Auto-fix what you can.
- Line length: **100** (configured in `ruff.toml`). Don't argue.
- No emoji in code or filenames. Emoji **are** allowed in user-facing strings (UI, emails) and in docs/markdown.

### 2.2 Type hints (mandatory)

Every public function, method, and module-level constant must have type hints.

```python
# Good
def hash_password(plain: str) -> str: ...
async def create_session(s: AsyncSession, user: User) -> Session: ...
COOKIE_NAME: str = "session"

# Bad
def hash_password(plain): ...
async def create_session(s, user): ...
```

Use Python 3.12 syntax: `list[int]`, `dict[str, X]`, `int | None`. **Never** use `Optional`, `List`, `Dict`, `Union` — they're old.

Run `uv run pyright app/` before committing. Treat any new error as a defect.

### 2.3 Imports

Group in this order, separated by blank lines (ruff/isort handles this):

1. Standard library
2. Third-party
3. First-party (`from app.xxx import ...`)
4. Local (`from .xxx import ...` — discouraged; prefer absolute)

Avoid wildcard imports except in `app/models/__init__.py` (re-exports).

### 2.4 Naming

- Modules: `snake_case.py`
- Classes: `PascalCase`
- Functions/variables: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Private: leading underscore `_internal_helper`
- Pydantic schemas: `XxxCreate`, `XxxUpdate`, `XxxOut` (request/response separation)

### 2.5 Docstrings

- Public services and complex functions: short docstring (1-3 lines, what + why)
- Routers/CRUD endpoints: skip docstring; FastAPI's auto-generated OpenAPI suffices
- Test functions: descriptive name is the doc; no docstring needed

```python
async def select_papers_for_task(s: AsyncSession, task: Task) -> list[Paper]:
    """Run the 4-stage filter pipeline (category → keyword → semantic → topN)
    against today's papers and return what should be delivered to this task."""
```

### 2.6 Strings

- Default to **double quotes** `"..."` (matches ruff format default)
- f-strings for interpolation, never `%` or `.format()`

---

## 3. Project Structure (where things go)

| Concern | Location |
|---|---|
| FastAPI routers | `app/routers/<domain>.py` |
| Business logic | `app/services/<thing>.py` |
| Cron jobs | `app/jobs/<job>.py` |
| SQLAlchemy ORM | `app/models/<domain>.py` |
| Pydantic schemas | `app/schemas/<domain>.py` |
| Shared deps (auth) | `app/deps.py` |
| App entry | `app/main.py` |
| Settings | `app/config.py` |
| Templates | `templates/<area>/<page>.html` |
| Static assets | `static/{css,js}/` |
| Migrations | `alembic/versions/NNNN_description.py` |
| Tests | `tests/{unit,integration}/test_<thing>.py` |
| Mocks/fixtures | `tests/fixtures/` and `tests/conftest.py` |

**Rule**: a router never imports a model directly for non-trivial logic. Routers call services; services touch models. Keep routers thin.

---

## 4. Async Discipline

- The whole app is async. Every DB interaction goes through `AsyncSession`.
- **Never** use synchronous DB calls or blocking IO inside request handlers / cron jobs.
- For external HTTP, use `httpx.AsyncClient`, never `requests`.
- For timing/sleeps, use `asyncio.sleep`, never `time.sleep`.

When you need to call sync code from async, wrap it in `await asyncio.to_thread(fn, *args)`.

---

## 5. Database

### 5.1 Migrations

- **All schema changes go through Alembic.** Never `op.execute("ALTER TABLE ...")` in regular code.
- Filename pattern: `NNNN_short_description.py` (zero-padded 4-digit revision).
- After editing models, run:
  ```bash
  uv run alembic revision --autogenerate -m "describe change"
  ```
  Then **read the generated migration**, fix anything weird (especially around JSON columns and SQLite-specific quirks), then `uv run alembic upgrade head`.
- For sqlite-vec virtual tables: hand-write `op.execute(...)` in the migration; autogen won't catch them.

### 5.2 Sessions

- Always use `async with session_scope() as s:` for DB work in services / jobs / scripts.
- In routers, use the same pattern. (No FastAPI dependency for DB session in MVP — keeps deps simple. We can revisit later if it becomes a pain.)
- One `session_scope()` per logical unit of work. Don't try to thread one session through multiple unrelated operations.

### 5.3 Queries

Use `select()` style (SQLAlchemy 2.0). Don't use legacy `.query(Model)`.

```python
# Good
result = await s.execute(select(User).where(User.email == email))
user = result.scalar_one_or_none()

# Bad (1.x style)
user = s.query(User).filter_by(email=email).first()
```

For complex SQL (sqlite-vec MATCH, recursive CTEs, etc.), `text()` is fine but always parameterize:

```python
# Good
await s.execute(text("INSERT INTO paper_vectors VALUES (:p, :e)"), {"p": pid, "e": blob})
```

---

## 6. Testing (TDD is non-negotiable)

### 6.1 The cycle

For every feature: **failing test → run to verify failure → minimal code → run to verify pass → commit**.

When a test passes on the first run, you wrote the test wrong. Make it actually fail first.

### 6.2 Layout

- `tests/unit/` — pure functions, no DB, no HTTP
- `tests/integration/` — uses `client` fixture (FastAPI TestClient via httpx); uses real SQLite (in-memory or temp file) reset per test

### 6.3 Conventions

- Test names: `test_<subject>_<expected_behavior>`. Read like sentences. Examples:
  - `test_login_sets_cookie`
  - `test_quota_blocks_third_task`
  - `test_unverified_cannot_create`
- Use the `client` fixture from `conftest.py` for HTTP tests. The DB is reset before each test.
- Helper functions in tests: prefix with `_` so pytest doesn't try to collect them. Place at top of test file.

### 6.4 Mocking external services

| Service | Mock strategy |
|---|---|
| arXiv API | `unittest.mock.patch("app.jobs.fetch_arxiv.fetch_recent", return_value=[...])` |
| OpenAI Embedding | Set `EMBEDDING_PROVIDER=mock` (default in tests). Use `MockBackend` from `app/services/embedding.py` |
| Resend Email | Set `EMAIL_BACKEND=mock` (default in tests). Inspect `MockEmailBackend.sent` |
| Time | Use `freezegun` or pass `now` parameter. **Never** use `datetime.utcnow()` directly in code that needs to be testable; pass `now` as parameter or use injectable clock |

### 6.5 What to test

- **Always**: happy path, primary error case (validation, auth, not-found)
- **Often**: edge cases that the spec calls out (e.g. quota at exactly the limit)
- **Sometimes**: rare error paths (DB unavailable, external API down) — only when there's specific recovery logic

Don't test framework internals (FastAPI routing, Pydantic validation correctness — those have their own tests).

---

## 7. Commits

### 7.1 Format

```
<type>: <component>: <what>

<optional body>

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

Types:
- `feat` — new feature
- `fix` — bug fix
- `docs` — documentation only
- `test` — test-only changes (rare; usually folded into `feat`)
- `refactor` — refactoring without behavior change
- `chore` — build, deps, tooling
- `perf` — performance improvement

Examples:
- `feat: auth: add login/logout/me with cookie sessions`
- `fix: digest: dedupe deliveries by (task_id, paper_id) instead of (user_id, paper_id)`
- `chore: bump pydantic to 2.10`

### 7.2 Cadence

- Commit at the end of every Task (per the implementation plan).
- Within a Task, commit at logical sub-points if the Task naturally splits (rare; most Tasks are single-commit).
- **Never** commit failing tests as the last step of a Task.
- **Never** force-push or rewrite history on `main`.

### 7.3 What to stage

Stage explicitly with `git add path/to/file`. Avoid `git add -A` / `git add .` — too easy to accidentally commit junk like `data/app.db` or `.env`.

### 7.4 Branch strategy

- MVP phase: solo dev, all commits direct to `main`
- Post-launch: decide on PR flow if multiple contributors join
- Tags: `v0.x.y` SemVer for releases

---

## 8. Configuration

### 8.1 Settings

- All runtime config goes through `app/config.py:Settings` (Pydantic BaseSettings).
- Settings are loaded from `.env` at startup. Never read env vars directly elsewhere.
- For tests: pytest sets env vars via `conftest.py` if needed; or set them inline with `monkeypatch.setenv`.

### 8.2 Secrets

- `SECRET_KEY`, `OPENAI_API_KEY`, `RESEND_API_KEY` etc. are secrets.
- **Never** commit secrets to the repo. `.env` is gitignored; `.env.example` lists keys with placeholder values.
- **Never** log secrets — review log output before merging anything that touches them.
- For local dev, use random/dev-only values in `.env`.

---

## 9. Logging

Use `structlog` for all application logs.

```python
import structlog
log = structlog.get_logger()

# In a function
log.info("user.registered", user_id=user.id, email=user.email)
log.warning("quota.exceeded", user_id=user.id, max=quota.max_tasks)
log.error("arxiv.fetch_failed", category=cat, error=str(exc))
```

- Event names: `noun.verb_past` (`user.registered`), `noun.adjective` (`quota.exceeded`), `noun.verb_failed` (`arxiv.fetch_failed`)
- Structured fields, not interpolation (`user_id=...`, not `f"user {uid}"`)
- **Never** log: passwords, raw tokens, full embedding vectors, full email bodies
- OK to log: user_id, email (already a key user identifier in this product), task_id, paper_id, counts, durations

---

## 10. Errors

### 10.1 In routers

- Validation errors: let Pydantic raise (FastAPI returns 422 automatically)
- Business rule violations: `raise HTTPException(status_code=4xx, detail="...")` with a user-readable message
- Authentication: `401`. Authorization (logged in but not allowed): `403`. Not found: `404`. Conflict (e.g. duplicate email): `409`. Rate limit: `429`.

### 10.2 In services

- Raise specific exception classes when behavior matters: `class TaskQuotaExceeded(Exception): ...`
- Routers catch service exceptions and translate to HTTPException
- For external API failures: retry transient errors with exponential backoff (max 3 attempts), surface persistent errors to caller

### 10.3 In cron jobs

- Wrap entire job in `cron_run(job_name)` context manager — it logs success/failure to `cron_runs` table
- Catch and log per-item errors so one bad item doesn't break the whole run
- Critical failure (DB unavailable, etc.): let the exception propagate out of the job; cron_run will mark it failed and email admin

---

## 11. Security Baselines

- Password hashing: bcrypt via passlib. Cost 12 (passlib default). Never store plaintext.
- Session tokens: `secrets.token_urlsafe(32)` (256 bits). HttpOnly cookies. `secure=True` in prod (set via `APP_ENV` check).
- Email verification + password reset tokens: same `secrets.token_urlsafe(32)`. 48h expiry. One-time use (set `used_at` after consumption).
- Email enumeration: `/forgot-password` always returns 200, regardless of whether email exists.
- CSRF: SPA-style POST forms use HTMX → for non-GET, set `X-CSRF-Token` header from a session-bound token. (Defer to v1.1 if needed; HTMX + SameSite=Lax cookie covers most cases.)
- File uploads: not in MVP. Defer to v2.

---

## 12. Memory Discipline

This deploys to a 2C2G server with **<500MB budget**. Be careful with:

- **Never** load entire `papers` table into memory. Always paginate or stream.
- Avoid `.all()` on large queries; prefer iteration.
- Embedding vectors are 1536 floats × 4 bytes = 6KB each. 10k vectors = 60MB. OK for a working set, not OK for "load all into RAM at once."
- Don't cache large templates in dev mode; production = pre-compile via Jinja2 environment.
- One uvicorn worker. Don't bump to multi-worker without re-checking memory.

---

## 13. Performance Notes

- arXiv API: 3.5s rate limit between calls. Don't parallelize.
- OpenAI embedding: batch up to 100 inputs per request when possible.
- Cron jobs: aim to finish well under their interval (e.g. `send_digests` runs every minute → must finish in <30s for any individual user).
- SQLite WAL: turn on (already in `app/db.py`). Multiple readers + 1 writer is fine.

---

## 14. Anti-Patterns (don't do these)

| ❌ Don't | ✅ Do instead |
|---|---|
| `time.sleep(...)` in async code | `await asyncio.sleep(...)` |
| `requests.get(...)` | `httpx.AsyncClient` |
| Bare `except:` | `except SpecificError:` or `except Exception:` (and re-raise/log) |
| `print(...)` for debug | `log.info("event", **fields)` |
| `assert` for runtime checks | `if not x: raise ValueError(...)` |
| Mutable default args | `def f(x: list[int] | None = None): x = x or []` |
| `from x import *` (except in `__init__`) | explicit imports |
| Reading `os.environ` directly | `Settings` instance |
| Catching exception just to re-raise | let it propagate |
| Storing config in module-level globals | `Settings`, fetched per-call |

---

## 15. When in Doubt

1. **Read the spec** (`docs/superpowers/specs/2026-05-04-xivlab-design.md`) — it has the answer for what to build.
2. **Read the implementation plan** (`docs/superpowers/plans/2026-05-04-xivlab-implementation.md`) — it has the answer for how to sequence work.
3. **Read this guide again** — it has the answer for code conventions.
4. **Pick the boring choice.** If two approaches both work, go with the one that's more conventional / has more boring testability.
5. If still stuck, **leave a `# TODO(xivlab):` comment** explaining the question and continue. Don't block on perfection.
