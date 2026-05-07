# Changelog

All notable changes to xivLab.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-05-07

The MVP. arXiv 早报 + PromptHub running on a single Sacurajima box, < 500MB RAM.

### Added

- **Auth** — register, email verification, login (cookie sessions), forgot/reset password.
- **Tasks (arXiv 早报)** — CRUD API + dashboard UI, max 2 tasks per user via per-user quota.
- **arXiv pipeline** — daily fetch cron pulls papers, embeds them via the configured provider (mock/openai/zhipu/siliconflow), and dedups against the existing corpus.
- **Digest filter** — 5-stage pipeline (category window → keyword match → semantic rerank against task interest description → email-channel dedup → top-N cap).
- **Email digest** — Jinja2 HTML + text templates rendered through the configured backend (mock/Resend), driven by per-user TZ-aware `send_digests` cron.
- **RSS** — per-task Atom feed authenticated by an opaque `rss_token` query parameter, plus a `refresh_rss` cron pre-rendering feeds to disk.
- **PromptHub** — public Prompts CRUD with daily 5-prompt limit, idempotent voting, copy-track 30s anti-spam, and view counters; 9 seeded categories.
- **PromptHub frontend** — home (9 categories × top 5), per-category list with hot/new sort, prompt detail with HTMX vote/copy, author dashboard with status badges + review notes, create/edit form.
- **Admin** — review queue (`/admin/queue`) + `approve` / `reject` JSON endpoints with optional review note.
- **Operations** — APScheduler wired via FastAPI lifespan; `/health` endpoint reporting last `fetch_arxiv` run; `backup` (sqlite3 .backup, 14-day retention), `cleanup` (expired sessions/tokens, old cron rows), and `refresh_rss` cron jobs.
- **CLIs** — `scripts/create_admin.py` (idempotent admin upsert), `scripts/check_health.py` (deploy smoke).
- **Deployment** — `deploy/xivlab.service` (systemd, MemoryMax=500M), `deploy/nginx.conf` (TLS via Let's Encrypt), `deploy/deploy.sh` (rsync + uv sync + alembic upgrade + systemctl restart + remote /health check).
- **Quality bars** — `pyright app/` clean, `ruff check / format` clean, full pytest suite green (213 tests covering unit + integration + e2e).

### Documentation

- [Design spec](docs/superpowers/specs/2026-05-04-xivlab-design.md)
- [28-task implementation plan](docs/superpowers/plans/2026-05-04-xivlab-implementation.md)
- [Development guide](docs/DEVELOPMENT_GUIDE.md)
- [/loop runner manual](docs/LOOP_RUNNER.md)

[0.1.0]: https://github.com/xivlab/xivlab/releases/tag/v0.1.0
