# xivLab Loop Status

**Last updated**: 2026-05-04T18:10:00+08:00
**Last completed Task**: T01 (Project Bootstrap — FastAPI skeleton + health endpoint)
**Next Task**: T02 (Database Foundation + All Schemas — alembic, sqlite-vec, all ORM models)
**Test suite**: green (1 passed)
**Last commit**: pending — see git log after this iteration

## Notes for next iteration

- Python in this venv is 3.13.5 (uv picked the highest available ≥3.12). The `pyproject.toml` `requires-python = ">=3.12"` is satisfied.
- `uv` was not installed locally at the start of this iteration; installed via `brew install uv` (got 0.11.8). This is a developer-machine setup step; the LOOP_RUNNER assumes uv is already available in subsequent iterations.
- pytest emits a warning "ignoring pytest config in pyproject.toml" because both `pytest.ini` and `[tool.pytest.ini_options]` exist. This is harmless — `pytest.ini` wins. If a future iteration wants to clean up, it can drop the `[tool.pytest.ini_options]` block from `pyproject.toml`. Per LOOP_RUNNER §4.4 ("If a Step is wrong"), I'm noting it here rather than diverging from the plan.
- `app/config.py` calls `DATA_DIR.mkdir(exist_ok=True)` at import time, which creates `./data/` whenever any test or app module is imported. Empty dir, gitignored contents — fine for now.
- `tests/conftest.py` uses `httpx.ASGITransport(app=app)`. Tests import `app.main`, which imports `app.config`, which calls `Settings()`. With no `.env` present (and `.env.example` not auto-loaded), the defaults are used. This is consistent with the spec.
- All four acceptance gates pass (pytest, ruff check, ruff format --check, pyright).

## Bash classifier note (operational, not a code issue)

During this iteration the auto-mode bash safety classifier was intermittently unavailable for ~5 minutes, blocking commands like `uv --version` / `uv sync`. It eventually recovered and the iteration completed normally. Future iterations may see similar blips — retry, or use `git status`-style commands which seem to be pre-classified.

## Open issues / TODOs surfaced this iteration

- (none — Task 01 is fully self-contained)

## What's next (T02 high-level reminder)

T02 needs:
- `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`, `alembic/versions/0001_initial_schema.py`
- `app/db.py` with async engine + sqlite-vec extension loading
- All ORM models: user, task, paper, prompt, billing, ops
- Tests: `tests/unit/test_models.py`, `tests/unit/test_migrations.py`
- The migration must hand-write the `paper_vectors` virtual table (sqlite-vec) — autogen won't catch it.
- Run `uv run alembic upgrade head` and verify tables created.
