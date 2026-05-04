# xivLab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **For `/loop` driven autonomous development:** read `docs/LOOP_RUNNER.md` first. The loop runner executes ONE Task per iteration, top-to-bottom. Each Task is self-contained: files, tests, code, commit are all specified.

**Goal:** Build the MVP of xivLab — a research-AI tools site with two modules (arXiv 早报 + PromptHub) — to a production-deployable state on Sacurajima (2 vCPU / 1.9GB RAM Ubuntu) with <500MB memory budget.

**Architecture:** Single FastAPI app, server-rendered with Jinja2/HTMX, SQLite + sqlite-vec for storage, APScheduler in-process for cron, deployed via systemd + nginx. See [`docs/superpowers/specs/2026-05-04-xivlab-design.md`](../specs/2026-05-04-xivlab-design.md) for full spec.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy 2.0 (async) / Pydantic v2 / SQLite + sqlite-vec / Alembic / Jinja2 / HTMX / Tailwind CDN / APScheduler / passlib[bcrypt] / Resend (email) / OpenAI SDK (embeddings only) / pytest / uv

---

## Conventions

These apply to every task. Read once, then assume them throughout.

### File paths
- All paths are relative to the project root: `/Users/tassel/Documents/Project/GitHub/xivlab/` (local) or `/opt/xivlab/` (server).
- Production app code lives in `app/`. Tests in `tests/`. Migrations in `alembic/versions/`.

### TDD discipline
- Every Task follows: **failing test → run to verify failure → minimal implementation → run to verify pass → commit**.
- Tests use `pytest` + `pytest-asyncio`. HTTP layer tests use `httpx.AsyncClient` against the FastAPI app.
- Mocks: external services (arXiv API, OpenAI Embedding, Resend) are mocked. NEVER call real external APIs in tests.

### Commit format
- `feat: <component>: <what>` for new features
- `test: <component>: <what>` for test-only commits (rare; usually pair with feat)
- `fix: <component>: <what>` for bug fixes
- `chore: <what>` for build/deps/tooling
- `docs: <what>` for documentation
- Always end commit message with: `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`

### Commit cadence
- Commit at the end of each Task's "Step: Commit" instruction.
- Never commit failing tests as the last step.

### Task acceptance criteria (universal)
A Task is "done" iff:
1. All tests in the task's `Test:` files pass: `uv run pytest tests/<path>`
2. Type-check passes: `uv run pyright app/` (or `uv run mypy app/` if pyright not installed)
3. Lint passes: `uv run ruff check app/ tests/`
4. Format clean: `uv run ruff format --check app/ tests/`
5. Final commit on `main` branch matches the format above.

### Mocks fixtures location
- `tests/fixtures/arxiv_response.xml` — sample arXiv API response
- `tests/fixtures/embedding_seed.py` — deterministic 1536-dim mock embedding by seed
- `tests/fixtures/factories.py` — factory_boy fixtures for ORM models

---

## File Structure (target)

```
xivlab/
├─ app/
│  ├─ __init__.py
│  ├─ main.py              # FastAPI app, lifespan, middleware mounting
│  ├─ config.py            # Pydantic Settings (env-driven)
│  ├─ db.py                # async engine, sessionmaker
│  ├─ deps.py              # FastAPI deps (current_user, current_session, require_admin)
│  ├─ scheduler.py         # APScheduler + job registration
│  ├─ models/
│  │  ├─ __init__.py
│  │  ├─ user.py           # User, Session, EmailVerificationToken, PasswordResetToken
│  │  ├─ task.py           # Task, TaskEmbedding, Delivery
│  │  ├─ paper.py          # Paper (papers + paper_vectors via sqlite-vec)
│  │  ├─ prompt.py         # PromptCategory, Prompt, PromptVote, PromptCopyEvent
│  │  ├─ billing.py        # UserCredits, CreditEvent, TaskQuota
│  │  └─ ops.py            # CronRun
│  ├─ schemas/             # Pydantic request/response models, file-per-domain
│  │  ├─ auth.py
│  │  ├─ tasks.py
│  │  ├─ prompts.py
│  │  └─ ops.py
│  ├─ routers/
│  │  ├─ auth.py           # /api/v1/auth/*
│  │  ├─ tasks.py          # /api/v1/tasks/*
│  │  ├─ prompts.py        # /api/v1/prompts/*
│  │  ├─ categories.py     # /api/v1/categories
│  │  ├─ admin.py          # /api/v1/admin/*
│  │  ├─ rss.py            # /rss/*
│  │  ├─ pages.py          # server-rendered HTML pages
│  │  └─ health.py         # /health
│  └─ services/
│     ├─ password.py       # bcrypt wrappers
│     ├─ session.py        # session creation/lookup/expiry
│     ├─ email.py          # Resend wrapper + mock backend for dev
│     ├─ tokens.py         # secure random tokens
│     ├─ arxiv_fetcher.py  # arxiv API client + parser
│     ├─ embedding.py      # provider-agnostic embedding caller
│     ├─ digest.py         # filter pipeline (stage 1-5) + delivery
│     ├─ feed_renderer.py  # Atom/RSS XML generation
│     ├─ quota.py          # task slot quota check
│     └─ slug.py           # slugify titles
├─ alembic/
│  ├─ env.py
│  ├─ script.py.mako
│  └─ versions/            # one file per migration
├─ templates/              # Jinja2
│  ├─ base.html
│  ├─ auth/                # login, register, verify, etc.
│  ├─ pages/               # home, category, prompt detail, create
│  ├─ dashboard/
│  ├─ admin/
│  └─ emails/              # digest.html, digest.txt
├─ static/
│  ├─ css/                 # any custom (most via Tailwind CDN)
│  └─ js/                  # htmx, alpine cdn fallback or local
├─ tests/
│  ├─ conftest.py          # shared fixtures (db, client, mocks)
│  ├─ fixtures/
│  ├─ unit/
│  └─ integration/
├─ scripts/
│  ├─ create_admin.py      # CLI: 创建 admin 用户
│  └─ check_health.py      # smoke test
├─ deploy/
│  ├─ xivlab.service       # systemd unit
│  ├─ nginx.conf           # nginx site
│  └─ deploy.sh            # build + ship to Sacurajima
├─ docs/
│  ├─ superpowers/specs/   # 设计文档
│  ├─ superpowers/plans/   # this file
│  ├─ DEVELOPMENT_GUIDE.md # 编码风格 / 测试规范
│  └─ LOOP_RUNNER.md       # /loop session 运行手册
├─ .env.example
├─ .gitignore
├─ pyproject.toml          # uv-managed
├─ uv.lock
├─ alembic.ini
├─ pytest.ini
├─ ruff.toml
└─ README.md
```

---

## Phased Roadmap (overview)

| Phase | Tasks | Goal |
|---|---|---|
| **0. Bootstrap** | T01–T02 | Project skeleton + config + DB foundation |
| **1. Auth** | T03–T07 | User registration through password reset |
| **2. Frontend base** | T08–T09 | Jinja2 + Tailwind + auth pages |
| **3. Module A: Tasks** | T10–T11 | Task CRUD API + dashboard UI |
| **4. Module A: arXiv pipeline** | T12–T14 | arXiv fetcher + embedding + daily cron |
| **5. Module A: Digest** | T15–T17 | Filter pipeline + email + send_digests cron |
| **6. Module A: RSS** | T18 | Atom feed + token-authed endpoint |
| **7. Module C: Prompts** | T19–T23 | CRUD + voting + UI + dashboard |
| **8. Admin** | T24 | Approve/reject queue |
| **9. Operations** | T25–T26 | Health + backup + cleanup |
| **10. Deployment** | T27 | systemd + nginx + deploy script |
| **11. Smoke test** | T28 | E2E flow + polish |

**Total: 28 Tasks**, designed for ~20 `/loop` iterations (some adjacent small tasks the runner may batch).

---

## Task 01: Project Bootstrap

**Files:**
- Create: `pyproject.toml`
- Create: `ruff.toml`
- Create: `pytest.ini`
- Create: `.env.example`
- Create: `app/__init__.py`
- Create: `app/main.py`
- Create: `app/config.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/test_smoke.py`

- [x] **Step 1: pyproject.toml**

```toml
[project]
name = "xivlab"
version = "0.1.0"
description = "Research AI tools — arXiv digest + PromptHub"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.32",
  "sqlalchemy[asyncio]>=2.0",
  "aiosqlite>=0.20",
  "alembic>=1.13",
  "pydantic>=2.9",
  "pydantic-settings>=2.5",
  "passlib[bcrypt]>=1.7",
  "python-multipart>=0.0.12",
  "jinja2>=3.1",
  "httpx>=0.27",
  "feedparser>=6.0",  # arxiv parsing
  "structlog>=24.4",
  "apscheduler>=3.10",
  "resend>=2.4",
  "openai>=1.50",  # embedding only
  "sqlite-vec>=0.1",
]

[dependency-groups]
dev = [
  "pytest>=8.3",
  "pytest-asyncio>=0.24",
  "factory-boy>=3.3",
  "ruff>=0.7",
  "pyright>=1.1",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.pyright]
include = ["app", "tests"]
pythonVersion = "3.12"
typeCheckingMode = "basic"
```

- [x] **Step 2: ruff.toml**

```toml
line-length = 100
target-version = "py312"

[lint]
select = ["E", "F", "W", "I", "B", "UP", "N", "RUF"]
ignore = ["E501"]
```

- [x] **Step 3: pytest.ini**

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
addopts = -v --tb=short
```

- [x] **Step 4: .env.example**

```
APP_ENV=dev
APP_BASE_URL=http://localhost:8001
SECRET_KEY=changeme-32bytes-hex-replace-in-prod
DATABASE_URL=sqlite+aiosqlite:///./data/app.db

# Email (dev: mock; prod: resend)
EMAIL_BACKEND=mock
RESEND_API_KEY=
RESEND_FROM_EMAIL=noreply@xivlab.local
ADMIN_EMAILS=admin@xivlab.local

# Embedding
EMBEDDING_PROVIDER=mock
EMBEDDING_MODEL=text-embedding-3-small
OPENAI_API_KEY=

# arXiv
ARXIV_CATEGORIES=cs.AI,cs.LG,cs.CL,cs.CV,cs.CR,cs.DB,cs.DC,cs.DS,cs.HC,cs.IR,stat.ML
```

- [x] **Step 5: app/config.py**

```python
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"
    app_base_url: str = "http://localhost:8001"
    secret_key: str = "changeme"
    database_url: str = "sqlite+aiosqlite:///./data/app.db"

    email_backend: str = "mock"  # 'mock' | 'resend'
    resend_api_key: str = ""
    resend_from_email: str = "noreply@xivlab.local"
    admin_emails: str = ""  # comma-separated

    embedding_provider: str = "mock"  # 'mock' | 'openai' | 'zhipu' | 'siliconflow'
    embedding_model: str = "text-embedding-3-small"
    openai_api_key: str = ""

    arxiv_categories: str = "cs.AI,cs.LG,cs.CL"

    @property
    def admin_email_list(self) -> list[str]:
        return [e.strip() for e in self.admin_emails.split(",") if e.strip()]

    @property
    def arxiv_category_list(self) -> list[str]:
        return [c.strip() for c in self.arxiv_categories.split(",") if c.strip()]


def get_settings() -> Settings:
    return Settings()


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
```

- [x] **Step 6: app/main.py (minimal)**

```python
from fastapi import FastAPI
from app.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="xivLab",
        description="Research AI tools — arXiv digest + PromptHub",
        version="0.1.0",
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "env": settings.app_env}

    return app


app = create_app()
```

- [x] **Step 7: tests/conftest.py (minimal)**

```python
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
```

- [x] **Step 8: tests/test_smoke.py**

```python
async def test_health_endpoint_returns_ok(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
```

- [x] **Step 9: Run uv sync and verify**

```bash
uv sync
uv run pytest tests/test_smoke.py -v
```

Expected: all tests pass; `app/` and `tests/` directories created.

- [x] **Step 10: Commit**

```bash
git add pyproject.toml ruff.toml pytest.ini .env.example app/ tests/ uv.lock
git commit -m "chore: bootstrap FastAPI skeleton with health endpoint

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 02: Database Foundation + All Schemas

**Files:**
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/script.py.mako`
- Create: `alembic/versions/0001_initial_schema.py`
- Create: `app/db.py`
- Create: `app/models/__init__.py`
- Create: `app/models/user.py`
- Create: `app/models/task.py`
- Create: `app/models/paper.py`
- Create: `app/models/prompt.py`
- Create: `app/models/billing.py`
- Create: `app/models/ops.py`
- Test: `tests/unit/test_models.py`
- Test: `tests/unit/test_migrations.py`

- [x] **Step 1: app/db.py**

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import sqlite_vec
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    pass


_settings = get_settings()
engine = create_async_engine(_settings.database_url, echo=False, future=True)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@event.listens_for(engine.sync_engine, "connect")
def _enable_extensions(dbapi_conn, _connection_record):
    # WAL mode + sqlite-vec
    dbapi_conn.execute("PRAGMA journal_mode=WAL")
    dbapi_conn.execute("PRAGMA foreign_keys=ON")
    dbapi_conn.enable_load_extension(True)
    sqlite_vec.load(dbapi_conn)
    dbapi_conn.enable_load_extension(False)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
```

- [x] **Step 2: app/models/user.py**

```python
from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    display_name: Mapped[str | None] = mapped_column(String(100))
    tz: Mapped[str] = mapped_column(String(64), default="Asia/Shanghai")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime)
    user_agent: Mapped[str | None] = mapped_column(Text)
    ip: Mapped[str | None] = mapped_column(String(64))


class EmailVerificationToken(Base):
    __tablename__ = "email_verification_tokens"
    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime)


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime)
```

- [x] **Step 3: app/models/task.py**

```python
from datetime import datetime
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    arxiv_categories: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    keywords: Mapped[list[str] | None] = mapped_column(JSON)
    min_keyword_match: Mapped[int] = mapped_column(Integer, default=1)
    interest_description: Mapped[str | None] = mapped_column(Text)
    max_papers_per_day: Mapped[int] = mapped_column(Integer, default=10)
    delivery_time: Mapped[str] = mapped_column(String(5), default="08:00")
    delivery_channels: Mapped[list[str]] = mapped_column(JSON, default=lambda: ["email"])
    rss_token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TaskEmbedding(Base):
    __tablename__ = "task_embeddings"
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True)
    embedding: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Delivery(Base):
    __tablename__ = "deliveries"
    __table_args__ = (
        UniqueConstraint("task_id", "paper_id", "channel", name="uq_deliveries_task_paper_channel"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    paper_id: Mapped[str] = mapped_column(String(64), ForeignKey("papers.id"))
    delivered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    channel: Mapped[str] = mapped_column(String(16))
    opened_at: Mapped[datetime | None] = mapped_column(DateTime)
    clicked_at: Mapped[datetime | None] = mapped_column(DateTime)
```

- [x] **Step 4: app/models/paper.py**

```python
from datetime import datetime
from sqlalchemy import JSON, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class Paper(Base):
    __tablename__ = "papers"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # arxiv id
    title: Mapped[str] = mapped_column(Text, nullable=False)
    abstract: Mapped[str] = mapped_column(Text, nullable=False)
    authors: Mapped[list[str]] = mapped_column(JSON, default=list)
    primary_category: Mapped[str | None] = mapped_column(String(32), index=True)
    all_categories: Mapped[list[str]] = mapped_column(JSON, default=list)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    pdf_url: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# paper_vectors is sqlite-vec virtual table; created via raw SQL in migration.
```

- [x] **Step 5: app/models/prompt.py**

```python
from datetime import datetime
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class PromptCategory(Base):
    __tablename__ = "prompt_categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    icon: Mapped[str | None] = mapped_column(String(64))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class Prompt(Base):
    __tablename__ = "prompts"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    category_id: Mapped[int] = mapped_column(ForeignKey("prompt_categories.id"), index=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    variables: Mapped[list[dict] | None] = mapped_column(JSON)
    example_input: Mapped[str | None] = mapped_column(Text)
    example_output: Mapped[str | None] = mapped_column(Text)
    author_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    language: Mapped[str] = mapped_column(String(8), nullable=False)
    upvotes: Mapped[int] = mapped_column(Integer, default=0)
    copies: Mapped[int] = mapped_column(Integer, default=0)
    views: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    review_note: Mapped[str | None] = mapped_column(Text)
    forked_from_id: Mapped[int | None] = mapped_column(ForeignKey("prompts.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PromptVote(Base):
    __tablename__ = "prompt_votes"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    prompt_id: Mapped[int] = mapped_column(ForeignKey("prompts.id"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PromptCopyEvent(Base):
    __tablename__ = "prompt_copy_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    prompt_id: Mapped[int] = mapped_column(ForeignKey("prompts.id"), index=True)
    user_or_ip: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

- [x] **Step 6: app/models/billing.py**

```python
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class UserCredits(Base):
    __tablename__ = "user_credits"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    balance: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CreditEvent(Base):
    __tablename__ = "credit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    ref_type: Mapped[str | None] = mapped_column(String(64))
    ref_id: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TaskQuota(Base):
    __tablename__ = "task_quotas"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    max_tasks: Mapped[int] = mapped_column(Integer, default=2)
    last_recalc: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

- [x] **Step 7: app/models/ops.py**

```python
from datetime import datetime
from sqlalchemy import JSON, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class CronRun(Base):
    __tablename__ = "cron_runs"
    __table_args__ = (Index("idx_cron_runs_job_started", "job_name", "started_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    job_name: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # 'running' | 'success' | 'failed'
    error_message: Mapped[str | None] = mapped_column(Text)
    job_metadata: Mapped[dict | None] = mapped_column(JSON)  # avoid name clash with SA metadata
```

- [x] **Step 8: app/models/__init__.py**

```python
from app.models.user import User, Session, EmailVerificationToken, PasswordResetToken
from app.models.task import Task, TaskEmbedding, Delivery
from app.models.paper import Paper
from app.models.prompt import PromptCategory, Prompt, PromptVote, PromptCopyEvent
from app.models.billing import UserCredits, CreditEvent, TaskQuota
from app.models.ops import CronRun

__all__ = [
    "User", "Session", "EmailVerificationToken", "PasswordResetToken",
    "Task", "TaskEmbedding", "Delivery",
    "Paper",
    "PromptCategory", "Prompt", "PromptVote", "PromptCopyEvent",
    "UserCredits", "CreditEvent", "TaskQuota",
    "CronRun",
]
```

- [x] **Step 9: alembic init + env.py**

Run: `uv run alembic init alembic`

Then replace `alembic/env.py` with:

```python
import asyncio
from logging.config import fileConfig
from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import get_settings
from app.db import Base
import app.models  # ensure models are imported  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", get_settings().database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


asyncio.run(run_migrations_online())
```

- [x] **Step 10: Generate initial migration**

```bash
uv run alembic revision --autogenerate -m "initial schema"
mv alembic/versions/*.py alembic/versions/0001_initial_schema.py
```

- [x] **Step 11: Append sqlite-vec virtual table to the migration**

In the generated `alembic/versions/0001_initial_schema.py`, add to `upgrade()` after the autogenerated content:

```python
op.execute("""
CREATE VIRTUAL TABLE paper_vectors USING vec0(
    paper_id TEXT PRIMARY KEY,
    embedding FLOAT[1536]
);
""")
```

And to `downgrade()` (insert at start, before autogenerated drops):

```python
op.execute("DROP TABLE IF EXISTS paper_vectors;")
```

- [x] **Step 12: Add seed migration for prompt_categories**

Create `alembic/versions/0002_seed_categories.py`:

```python
"""seed prompt_categories

Revision ID: 0002_seed_categories
Revises: 0001_initial_schema
"""
from alembic import op

revision = "0002_seed_categories"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None

CATEGORIES = [
    ("paper-writing", "论文写作", "润色、改写、cover letter、rebuttal", "✏️", 10),
    ("paper-reading", "论文阅读", "摘要、批判、问答", "📖", 20),
    ("code", "代码", "解释、生成、调试、审计", "💻", 30),
    ("data-analysis", "数据分析", "matplotlib、pandas、可视化", "📊", 40),
    ("experiment-design", "实验设计", "hyperparameter、ablation", "🧪", 50),
    ("academic-english", "学术英语", "润色、翻译", "🌐", 60),
    ("literature-review", "文献调研", "综述、相关工作", "📚", 70),
    ("admin", "行政事务", "推荐信、求职信、邮件", "📝", 80),
    ("misc", "杂项", "其他场景", "🗂️", 90),
]


def upgrade() -> None:
    for slug, name, desc, icon, order in CATEGORIES:
        op.execute(
            f"INSERT INTO prompt_categories (slug, name, description, icon, sort_order) "
            f"VALUES ('{slug}', '{name}', '{desc}', '{icon}', {order});"
        )


def downgrade() -> None:
    op.execute("DELETE FROM prompt_categories;")
```

- [x] **Step 13: Run migrations + verify**

```bash
uv run alembic upgrade head
ls data/app.db && uv run sqlite3 data/app.db "SELECT slug FROM prompt_categories;"
```

Expected: 9 category slugs printed.

- [x] **Step 14: tests/unit/test_models.py**

```python
from sqlalchemy import select
from app.db import session_scope
from app.models import User, PromptCategory


async def test_create_user_persists():
    async with session_scope() as s:
        s.add(User(email="t@x.dev", password_hash="x", display_name="T"))
        await s.commit()
        result = await s.execute(select(User).where(User.email == "t@x.dev"))
        user = result.scalar_one()
        assert user.email == "t@x.dev"
        assert user.email_verified is False
        await s.delete(user)
        await s.commit()


async def test_categories_seeded():
    async with session_scope() as s:
        result = await s.execute(select(PromptCategory))
        cats = result.scalars().all()
        assert len(cats) == 9
        slugs = {c.slug for c in cats}
        assert "paper-writing" in slugs
        assert "code" in slugs
```

- [x] **Step 15: Run tests**

```bash
uv run pytest tests/unit/test_models.py -v
```

Expected: PASS.

- [x] **Step 16: Commit**

```bash
git add alembic.ini alembic/ app/db.py app/models/ tests/unit/
git commit -m "feat: db: add SQLAlchemy models, alembic migration, sqlite-vec, seed categories

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 03: Auth — Password Hashing + Register Endpoint

**Files:**
- Create: `app/services/password.py`
- Create: `app/services/tokens.py`
- Create: `app/schemas/auth.py`
- Create: `app/routers/auth.py`
- Modify: `app/main.py` (mount router)
- Test: `tests/unit/test_password.py`
- Test: `tests/integration/test_auth_register.py`

- [x] **Step 1: Test for password.hash + verify (RED)**

`tests/unit/test_password.py`:

```python
from app.services.password import hash_password, verify_password


def test_hash_then_verify_succeeds():
    h = hash_password("secret123")
    assert h != "secret123"
    assert verify_password("secret123", h) is True


def test_verify_wrong_password_fails():
    h = hash_password("secret123")
    assert verify_password("wrong", h) is False
```

Run: `uv run pytest tests/unit/test_password.py -v` → FAIL (module missing).

- [x] **Step 2: Implement app/services/password.py**

```python
from passlib.context import CryptContext

_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return _ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _ctx.verify(plain, hashed)
```

Run tests → PASS.

- [x] **Step 3: app/services/tokens.py**

```python
import secrets


def random_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)
```

- [x] **Step 4: Test register endpoint (RED)**

`tests/integration/test_auth_register.py`:

```python
async def test_register_creates_unverified_user(client):
    r = await client.post("/api/v1/auth/register",
                          json={"email": "alice@example.com", "password": "passw0rd!", "display_name": "Alice"})
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "alice@example.com"
    assert body["email_verified"] is False
    assert "id" in body


async def test_register_duplicate_email_409(client):
    await client.post("/api/v1/auth/register",
                      json={"email": "bob@example.com", "password": "passw0rd!"})
    r = await client.post("/api/v1/auth/register",
                          json={"email": "bob@example.com", "password": "passw0rd!"})
    assert r.status_code == 409


async def test_register_short_password_422(client):
    r = await client.post("/api/v1/auth/register",
                          json={"email": "c@example.com", "password": "x"})
    assert r.status_code == 422
```

(Tests need a fresh DB per test; conftest will be expanded later. For now if collisions occur, tests assume happy path.)

- [x] **Step 5: app/schemas/auth.py**

```python
from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = Field(default=None, max_length=100)


class UserPublic(BaseModel):
    id: int
    email: EmailStr
    email_verified: bool
    display_name: str | None
```

- [x] **Step 6: app/routers/auth.py (register only for now)**

```python
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.db import session_scope
from app.models import User
from app.schemas.auth import RegisterRequest, UserPublic
from app.services.password import hash_password

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest) -> UserPublic:
    async with session_scope() as s:
        existing = await s.execute(select(User).where(User.email == payload.email))
        if existing.scalar_one_or_none():
            raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
        user = User(
            email=payload.email,
            password_hash=hash_password(payload.password),
            display_name=payload.display_name,
        )
        s.add(user)
        await s.commit()
        await s.refresh(user)
        return UserPublic.model_validate(user, from_attributes=True)
```

- [x] **Step 7: Mount router in app/main.py**

Modify `create_app()` in `app/main.py`:

```python
from app.routers import auth as auth_router
# ...
app.include_router(auth_router.router)
```

- [x] **Step 8: Add fresh-db fixture in conftest.py**

Append to `tests/conftest.py`:

```python
import pytest_asyncio
from app.db import engine, Base


@pytest_asyncio.fixture(autouse=True)
async def _reset_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    # also re-seed prompt categories
    from app.models import PromptCategory
    from app.db import session_scope
    async with session_scope() as s:
        for slug, name, desc, icon, order in [
            ("paper-writing", "论文写作", "", "✏️", 10),
            ("paper-reading", "论文阅读", "", "📖", 20),
            ("code", "代码", "", "💻", 30),
            ("data-analysis", "数据分析", "", "📊", 40),
            ("experiment-design", "实验设计", "", "🧪", 50),
            ("academic-english", "学术英语", "", "🌐", 60),
            ("literature-review", "文献调研", "", "📚", 70),
            ("admin", "行政事务", "", "📝", 80),
            ("misc", "杂项", "", "🗂️", 90),
        ]:
            s.add(PromptCategory(slug=slug, name=name, description=desc, icon=icon, sort_order=order))
        await s.commit()
    yield
```

- [x] **Step 9: Run tests**

```bash
uv run pytest tests/integration/test_auth_register.py tests/unit/test_password.py -v
```

Expected: ALL PASS.

- [x] **Step 10: Commit**

```bash
git add app/services/password.py app/services/tokens.py app/schemas/auth.py app/routers/auth.py app/main.py tests/
git commit -m "feat: auth: add register endpoint with bcrypt password hashing

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 04: Auth — Login + Sessions + current_user

**Files:**
- Create: `app/services/session.py`
- Create: `app/deps.py`
- Modify: `app/schemas/auth.py` (LoginRequest, SessionInfo)
- Modify: `app/routers/auth.py` (login, logout)
- Test: `tests/integration/test_auth_login.py`

- [x] **Step 1: Test login + cookie set (RED)**

`tests/integration/test_auth_login.py`:

```python
async def test_login_sets_cookie(client):
    await client.post("/api/v1/auth/register",
                      json={"email": "u1@x.dev", "password": "passw0rd!"})
    r = await client.post("/api/v1/auth/login",
                          json={"email": "u1@x.dev", "password": "passw0rd!"})
    assert r.status_code == 200
    assert "session" in r.cookies


async def test_login_wrong_password_401(client):
    await client.post("/api/v1/auth/register",
                      json={"email": "u2@x.dev", "password": "passw0rd!"})
    r = await client.post("/api/v1/auth/login",
                          json={"email": "u2@x.dev", "password": "wrong"})
    assert r.status_code == 401


async def test_me_endpoint_requires_session(client):
    r = await client.get("/api/v1/me")
    assert r.status_code == 401


async def test_me_endpoint_returns_user(client):
    await client.post("/api/v1/auth/register",
                      json={"email": "u3@x.dev", "password": "passw0rd!"})
    await client.post("/api/v1/auth/login",
                      json={"email": "u3@x.dev", "password": "passw0rd!"})
    r = await client.get("/api/v1/me")
    assert r.status_code == 200
    assert r.json()["email"] == "u3@x.dev"


async def test_logout_clears_cookie(client):
    await client.post("/api/v1/auth/register",
                      json={"email": "u4@x.dev", "password": "passw0rd!"})
    await client.post("/api/v1/auth/login",
                      json={"email": "u4@x.dev", "password": "passw0rd!"})
    r = await client.post("/api/v1/auth/logout")
    assert r.status_code == 204
    r2 = await client.get("/api/v1/me")
    assert r2.status_code == 401
```

Run → FAIL.

- [x] **Step 2: app/services/session.py**

```python
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Session as DbSession, User
from app.services.tokens import random_token

SESSION_LIFETIME = timedelta(days=30)


async def create_session(s: AsyncSession, user: User, *, user_agent: str | None = None, ip: str | None = None) -> DbSession:
    sid = random_token(32)
    sess = DbSession(
        id=sid,
        user_id=user.id,
        expires_at=datetime.utcnow() + SESSION_LIFETIME,
        last_seen_at=datetime.utcnow(),
        user_agent=user_agent,
        ip=ip,
    )
    s.add(sess)
    await s.commit()
    return sess


async def get_session(s: AsyncSession, sid: str) -> DbSession | None:
    result = await s.execute(select(DbSession).where(DbSession.id == sid))
    sess = result.scalar_one_or_none()
    if not sess or sess.expires_at < datetime.utcnow():
        return None
    return sess


async def delete_session(s: AsyncSession, sid: str) -> None:
    sess = await get_session(s, sid)
    if sess:
        await s.delete(sess)
        await s.commit()


async def slide_session(s: AsyncSession, sess: DbSession) -> None:
    sess.expires_at = datetime.utcnow() + SESSION_LIFETIME
    sess.last_seen_at = datetime.utcnow()
    await s.commit()
```

- [x] **Step 3: app/deps.py**

```python
from typing import Annotated
from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy import select
from app.db import session_scope
from app.models import User
from app.services.session import get_session, slide_session

COOKIE_NAME = "session"


async def current_user(session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None) -> User:
    if not session:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    async with session_scope() as s:
        sess = await get_session(s, session)
        if not sess:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
        await slide_session(s, sess)
        user = (await s.execute(select(User).where(User.id == sess.user_id))).scalar_one()
        return user


async def require_admin(user: Annotated[User, Depends(current_user)]) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin only")
    return user


async def require_email_verified(user: Annotated[User, Depends(current_user)]) -> User:
    if not user.email_verified:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Email not verified")
    return user
```

- [x] **Step 4: Add LoginRequest to schemas/auth.py**

```python
class LoginRequest(BaseModel):
    email: EmailStr
    password: str
```

- [x] **Step 5: Add login + logout + /me to routers**

Append to `app/routers/auth.py`:

```python
from fastapi import Depends, Response
from app.deps import current_user, COOKIE_NAME
from app.services.password import verify_password
from app.services.session import create_session, delete_session
from app.schemas.auth import LoginRequest


@router.post("/login")
async def login(payload: LoginRequest, response: Response, request: Request):
    async with session_scope() as s:
        result = await s.execute(select(User).where(User.email == payload.email))
        user = result.scalar_one_or_none()
        if not user or not verify_password(payload.password, user.password_hash):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bad credentials")
        sess = await create_session(s, user,
                                    user_agent=request.headers.get("user-agent"),
                                    ip=request.client.host if request.client else None)
    response.set_cookie(
        COOKIE_NAME, sess.id,
        httponly=True, samesite="lax",
        secure=False,  # set True in prod via APP_ENV check
        max_age=30 * 24 * 3600,
    )
    return {"ok": True}


@router.post("/logout", status_code=204)
async def logout(response: Response, session: str | None = Cookie(default=None, alias=COOKIE_NAME)):
    if session:
        async with session_scope() as s:
            await delete_session(s, session)
    response.delete_cookie(COOKIE_NAME)
```

Add `Cookie` and `Request` imports at top.

- [x] **Step 6: Create /api/v1/me router**

Create `app/routers/me.py`:

```python
from typing import Annotated
from fastapi import APIRouter, Depends
from app.deps import current_user
from app.models import User
from app.schemas.auth import UserPublic

router = APIRouter(prefix="/api/v1/me", tags=["me"])


@router.get("", response_model=UserPublic)
async def me(user: Annotated[User, Depends(current_user)]) -> UserPublic:
    return UserPublic.model_validate(user, from_attributes=True)
```

Mount in `app/main.py`:
```python
from app.routers import me as me_router
app.include_router(me_router.router)
```

- [x] **Step 7: Run tests**

```bash
uv run pytest tests/integration/test_auth_login.py -v
```

Expected: PASS.

- [x] **Step 8: Commit**

```bash
git add app/services/session.py app/deps.py app/schemas/auth.py app/routers/ tests/
git commit -m "feat: auth: add login/logout/me with cookie sessions

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 05: Auth — Email Service + Verification

**Files:**
- Create: `app/services/email.py`
- Modify: `app/routers/auth.py` (verify-email endpoint, send verification on register)
- Test: `tests/unit/test_email_mock.py`
- Test: `tests/integration/test_email_verification.py`

- [x] **Step 1: app/services/email.py with mock + Resend backends**

```python
from dataclasses import dataclass, field
from app.config import get_settings


@dataclass
class SentEmail:
    to: str
    subject: str
    html: str
    text: str


class MockEmailBackend:
    sent: list[SentEmail] = []

    @classmethod
    def reset(cls) -> None:
        cls.sent.clear()

    @classmethod
    async def send(cls, to: str, subject: str, html: str, text: str) -> None:
        cls.sent.append(SentEmail(to=to, subject=subject, html=html, text=text))


class ResendBackend:
    @classmethod
    async def send(cls, to: str, subject: str, html: str, text: str) -> None:
        import resend
        settings = get_settings()
        resend.api_key = settings.resend_api_key
        resend.Emails.send({
            "from": settings.resend_from_email,
            "to": [to],
            "subject": subject,
            "html": html,
            "text": text,
        })


def get_backend():
    settings = get_settings()
    if settings.email_backend == "resend":
        return ResendBackend
    return MockEmailBackend


async def send_email(to: str, subject: str, html: str, text: str) -> None:
    backend = get_backend()
    await backend.send(to, subject, html, text)
```

- [x] **Step 2: Test email mock**

`tests/unit/test_email_mock.py`:

```python
from app.services.email import MockEmailBackend, send_email


async def test_mock_records_sent_email():
    MockEmailBackend.reset()
    await send_email(to="x@y.dev", subject="Hi", html="<p>h</p>", text="h")
    assert len(MockEmailBackend.sent) == 1
    assert MockEmailBackend.sent[0].to == "x@y.dev"
```

Run → PASS (mock is the default backend in tests since `EMAIL_BACKEND=mock`).

- [x] **Step 3: Test verification flow (RED)**

`tests/integration/test_email_verification.py`:

```python
from sqlalchemy import select
from app.db import session_scope
from app.models import EmailVerificationToken
from app.services.email import MockEmailBackend


async def test_register_sends_verification_email(client):
    MockEmailBackend.reset()
    await client.post("/api/v1/auth/register",
                      json={"email": "v1@x.dev", "password": "passw0rd!"})
    assert any(m.to == "v1@x.dev" and "verify" in m.subject.lower()
               for m in MockEmailBackend.sent)


async def test_verify_email_marks_user_verified(client):
    MockEmailBackend.reset()
    await client.post("/api/v1/auth/register",
                      json={"email": "v2@x.dev", "password": "passw0rd!"})
    async with session_scope() as s:
        token = (await s.execute(select(EmailVerificationToken))).scalar_one().token
    r = await client.post(f"/api/v1/auth/verify-email/{token}")
    assert r.status_code == 200
    # user should now be verified
    await client.post("/api/v1/auth/login",
                      json={"email": "v2@x.dev", "password": "passw0rd!"})
    me = await client.get("/api/v1/me")
    assert me.json()["email_verified"] is True


async def test_verify_email_invalid_token_404(client):
    r = await client.post("/api/v1/auth/verify-email/invalid-token-xyz")
    assert r.status_code == 404
```

Run → FAIL.

- [x] **Step 4: Augment register to issue token + send email**

Modify `app/routers/auth.py` register handler:

```python
from datetime import datetime, timedelta
from app.models import EmailVerificationToken
from app.services.email import send_email
from app.services.tokens import random_token
from app.config import get_settings


@router.post("/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest) -> UserPublic:
    async with session_scope() as s:
        existing = await s.execute(select(User).where(User.email == payload.email))
        if existing.scalar_one_or_none():
            raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
        user = User(
            email=payload.email,
            password_hash=hash_password(payload.password),
            display_name=payload.display_name,
        )
        s.add(user)
        await s.flush()

        token = EmailVerificationToken(
            token=random_token(32),
            user_id=user.id,
            expires_at=datetime.utcnow() + timedelta(hours=48),
        )
        s.add(token)
        await s.commit()
        await s.refresh(user)

    settings = get_settings()
    verify_url = f"{settings.app_base_url}/verify-email/{token.token}"
    await send_email(
        to=user.email,
        subject="[xivLab] Verify your email",
        html=f'<p>Click to verify: <a href="{verify_url}">{verify_url}</a></p>',
        text=f"Click to verify: {verify_url}",
    )
    return UserPublic.model_validate(user, from_attributes=True)
```

- [x] **Step 5: Add verify-email endpoint**

Append to `app/routers/auth.py`:

```python
@router.post("/verify-email/{token}")
async def verify_email(token: str):
    async with session_scope() as s:
        result = await s.execute(
            select(EmailVerificationToken).where(EmailVerificationToken.token == token)
        )
        evt = result.scalar_one_or_none()
        if not evt or evt.used_at is not None or evt.expires_at < datetime.utcnow():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Invalid or expired token")
        user = (await s.execute(select(User).where(User.id == evt.user_id))).scalar_one()
        user.email_verified = True
        evt.used_at = datetime.utcnow()
        await s.commit()
    return {"ok": True}
```

- [x] **Step 6: Run tests**

```bash
uv run pytest tests/integration/test_email_verification.py tests/unit/test_email_mock.py -v
```

Expected: PASS.

- [x] **Step 7: Commit**

```bash
git add app/services/email.py app/routers/auth.py tests/
git commit -m "feat: auth: send verification email on register; add verify-email endpoint

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 06: Auth — Password Reset

**Files:**
- Modify: `app/schemas/auth.py` (ForgotPasswordRequest, ResetPasswordRequest)
- Modify: `app/routers/auth.py`
- Test: `tests/integration/test_password_reset.py`

- [ ] **Step 1: Test (RED)**

`tests/integration/test_password_reset.py`:

```python
from sqlalchemy import select
from app.db import session_scope
from app.models import PasswordResetToken
from app.services.email import MockEmailBackend


async def test_forgot_password_sends_email(client):
    await client.post("/api/v1/auth/register", json={"email": "p1@x.dev", "password": "old123!"})
    MockEmailBackend.reset()
    r = await client.post("/api/v1/auth/forgot-password", json={"email": "p1@x.dev"})
    assert r.status_code == 200
    assert any(m.to == "p1@x.dev" and "reset" in m.subject.lower()
               for m in MockEmailBackend.sent)


async def test_reset_password_changes_password(client):
    await client.post("/api/v1/auth/register", json={"email": "p2@x.dev", "password": "old1234!"})
    await client.post("/api/v1/auth/forgot-password", json={"email": "p2@x.dev"})
    async with session_scope() as s:
        token = (await s.execute(select(PasswordResetToken))).scalars().first().token
    r = await client.post("/api/v1/auth/reset-password",
                          json={"token": token, "new_password": "new1234!"})
    assert r.status_code == 200
    # new password works
    r1 = await client.post("/api/v1/auth/login",
                           json={"email": "p2@x.dev", "password": "new1234!"})
    assert r1.status_code == 200
    # old fails
    r2 = await client.post("/api/v1/auth/login",
                           json={"email": "p2@x.dev", "password": "old1234!"})
    assert r2.status_code == 401


async def test_forgot_unknown_email_silent(client):
    # Don't reveal whether email exists
    r = await client.post("/api/v1/auth/forgot-password", json={"email": "ghost@x.dev"})
    assert r.status_code == 200
```

- [ ] **Step 2: Schemas**

```python
class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)
```

- [ ] **Step 3: Endpoints in routers/auth.py**

```python
@router.post("/forgot-password")
async def forgot_password(payload: ForgotPasswordRequest):
    async with session_scope() as s:
        user = (await s.execute(select(User).where(User.email == payload.email))).scalar_one_or_none()
        if user:
            tok = PasswordResetToken(
                token=random_token(32),
                user_id=user.id,
                expires_at=datetime.utcnow() + timedelta(hours=48),
            )
            s.add(tok)
            await s.commit()
            settings = get_settings()
            url = f"{settings.app_base_url}/reset-password/{tok.token}"
            await send_email(
                to=user.email,
                subject="[xivLab] Reset your password",
                html=f'<p>Click to reset: <a href="{url}">{url}</a></p>',
                text=f"Click to reset: {url}",
            )
    return {"ok": True}


@router.post("/reset-password")
async def reset_password(payload: ResetPasswordRequest):
    async with session_scope() as s:
        result = await s.execute(
            select(PasswordResetToken).where(PasswordResetToken.token == payload.token)
        )
        tok = result.scalar_one_or_none()
        if not tok or tok.used_at is not None or tok.expires_at < datetime.utcnow():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Invalid or expired token")
        user = (await s.execute(select(User).where(User.id == tok.user_id))).scalar_one()
        user.password_hash = hash_password(payload.new_password)
        tok.used_at = datetime.utcnow()
        await s.commit()
    return {"ok": True}
```

Add `PasswordResetToken` and `ForgotPasswordRequest`/`ResetPasswordRequest` to imports.

- [ ] **Step 4: Run tests + commit**

```bash
uv run pytest tests/integration/test_password_reset.py -v
git add app/schemas/auth.py app/routers/auth.py tests/
git commit -m "feat: auth: add forgot-password and reset-password endpoints

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 07: Frontend Foundation — Base Templates + Auth Pages

**Files:**
- Create: `templates/base.html`
- Create: `templates/auth/login.html`
- Create: `templates/auth/register.html`
- Create: `templates/auth/verify_pending.html`
- Create: `templates/auth/forgot_password.html`
- Create: `templates/auth/reset_password.html`
- Create: `app/routers/pages.py`
- Modify: `app/main.py` (StaticFiles + pages router)
- Test: `tests/integration/test_pages_auth.py`

- [ ] **Step 1: Test renders (RED)**

`tests/integration/test_pages_auth.py`:

```python
async def test_login_page_renders(client):
    r = await client.get("/login")
    assert r.status_code == 200
    assert "<form" in r.text
    assert "email" in r.text


async def test_register_page_renders(client):
    r = await client.get("/register")
    assert r.status_code == 200
    assert "Register" in r.text or "注册" in r.text


async def test_register_form_post_creates_user(client):
    r = await client.post("/register",
                          data={"email": "f1@x.dev", "password": "passw0rd!", "display_name": "F"},
                          follow_redirects=False)
    # Expect redirect to verify-pending after successful registration
    assert r.status_code in (302, 303)
```

- [ ] **Step 2: templates/base.html**

```html
<!doctype html>
<html lang="zh">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{% block title %}xivLab{% endblock %}</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://unpkg.com/htmx.org@2.0.3"></script>
  <script defer src="https://unpkg.com/alpinejs@3"></script>
</head>
<body class="bg-zinc-50 text-zinc-900 antialiased">
  <header class="border-b bg-white">
    <nav class="mx-auto max-w-6xl flex items-center justify-between px-4 py-3">
      <a href="/" class="font-semibold text-lg">🧪 xivLab</a>
      <div class="space-x-4 text-sm">
        <a href="/" class="hover:underline">Prompts</a>
        <a href="/dashboard" class="hover:underline">Dashboard</a>
        {% if user %}
          <span class="text-zinc-500">{{ user.display_name or user.email }}</span>
          <form action="/api/v1/auth/logout" method="post" class="inline">
            <button class="hover:underline">Logout</button>
          </form>
        {% else %}
          <a href="/login" class="hover:underline">Login</a>
          <a href="/register" class="hover:underline font-medium">Register</a>
        {% endif %}
      </div>
    </nav>
  </header>
  <main class="mx-auto max-w-6xl px-4 py-8">
    {% block content %}{% endblock %}
  </main>
  <footer class="mx-auto max-w-6xl px-4 py-8 text-xs text-zinc-500">
    xivLab — for researchers, by researchers.
  </footer>
</body>
</html>
```

- [ ] **Step 3: auth pages (login.html, register.html, etc.)**

`templates/auth/login.html`:
```html
{% extends "base.html" %}
{% block title %}Login · xivLab{% endblock %}
{% block content %}
<div class="max-w-md mx-auto bg-white border rounded-lg p-6">
  <h1 class="text-xl font-semibold mb-4">Login</h1>
  {% if error %}<p class="text-red-600 text-sm mb-3">{{ error }}</p>{% endif %}
  <form method="post" action="/login" class="space-y-3">
    <input type="email" name="email" placeholder="Email" required class="w-full border rounded px-3 py-2"/>
    <input type="password" name="password" placeholder="Password" required class="w-full border rounded px-3 py-2"/>
    <button class="w-full bg-zinc-900 text-white rounded py-2">Sign in</button>
  </form>
  <p class="text-sm text-zinc-500 mt-4">
    No account? <a href="/register" class="underline">Register</a> · 
    <a href="/forgot-password" class="underline">Forgot password</a>
  </p>
</div>
{% endblock %}
```

`templates/auth/register.html`:
```html
{% extends "base.html" %}
{% block content %}
<div class="max-w-md mx-auto bg-white border rounded-lg p-6">
  <h1 class="text-xl font-semibold mb-4">Register</h1>
  {% if error %}<p class="text-red-600 text-sm mb-3">{{ error }}</p>{% endif %}
  <form method="post" action="/register" class="space-y-3">
    <input type="email" name="email" placeholder="Email" required class="w-full border rounded px-3 py-2"/>
    <input type="text" name="display_name" placeholder="Display name (optional)" class="w-full border rounded px-3 py-2"/>
    <input type="password" name="password" placeholder="Password (8+ chars)" required minlength="8" class="w-full border rounded px-3 py-2"/>
    <button class="w-full bg-zinc-900 text-white rounded py-2">Create account</button>
  </form>
</div>
{% endblock %}
```

`templates/auth/verify_pending.html`:
```html
{% extends "base.html" %}
{% block content %}
<div class="max-w-md mx-auto bg-white border rounded-lg p-6 text-center">
  <h1 class="text-xl font-semibold mb-4">Check your inbox 📧</h1>
  <p class="text-zinc-700">We sent a verification link to <strong>{{ email }}</strong>. Click it to activate your account.</p>
</div>
{% endblock %}
```

(Create `forgot_password.html` and `reset_password.html` similarly — simple forms posting to the corresponding API endpoints.)

- [ ] **Step 4: app/routers/pages.py**

```python
from typing import Annotated
from fastapi import APIRouter, Cookie, Depends, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import PROJECT_ROOT
from app.deps import current_user, COOKIE_NAME
from app.models import User
from app.schemas.auth import RegisterRequest

templates = Jinja2Templates(directory=str(PROJECT_ROOT / "templates"))
router = APIRouter()


async def _try_user(session: str | None) -> User | None:
    if not session:
        return None
    try:
        return await current_user(session=session)
    except HTTPException:
        return None


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, session: str | None = Cookie(default=None, alias=COOKIE_NAME)):
    user = await _try_user(session)
    return templates.TemplateResponse("auth/login.html", {"request": request, "user": user})


@router.post("/login")
async def login_submit(email: Annotated[str, Form()], password: Annotated[str, Form()], request: Request):
    # Delegate to the API by reusing the service code; for brevity, call API internally
    from app.routers.auth import login as api_login
    from app.schemas.auth import LoginRequest
    response = Response()
    try:
        await api_login(LoginRequest(email=email, password=password), response, request)
    except HTTPException:
        return templates.TemplateResponse(
            "auth/login.html",
            {"request": request, "user": None, "error": "Bad credentials"},
            status_code=401,
        )
    redirect = RedirectResponse("/dashboard", status_code=303)
    redirect.raw_headers.extend(response.raw_headers)  # propagate Set-Cookie
    return redirect


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("auth/register.html", {"request": request, "user": None})


@router.post("/register")
async def register_submit(
    request: Request,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    display_name: Annotated[str | None, Form()] = None,
):
    from app.routers.auth import register as api_register
    try:
        await api_register(RegisterRequest(email=email, password=password, display_name=display_name))
    except HTTPException as e:
        return templates.TemplateResponse(
            "auth/register.html",
            {"request": request, "user": None, "error": e.detail},
            status_code=e.status_code,
        )
    return templates.TemplateResponse(
        "auth/verify_pending.html",
        {"request": request, "user": None, "email": email},
        status_code=303,
        headers={"Location": "/verify-pending"},
    )
```

- [ ] **Step 5: Mount router + StaticFiles in main.py**

```python
from fastapi.staticfiles import StaticFiles
from app.routers import pages as pages_router
from app.config import PROJECT_ROOT

app.mount("/static", StaticFiles(directory=str(PROJECT_ROOT / "static")), name="static")
app.include_router(pages_router.router)
```

(Create empty `static/` dir if missing.)

- [ ] **Step 6: Run tests + commit**

```bash
uv run pytest tests/integration/test_pages_auth.py -v
git add templates/ static/.gitkeep app/routers/pages.py app/main.py tests/
git commit -m "feat: pages: add base layout and auth pages (login/register/verify-pending)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 08: Module A — Tasks CRUD API + Quota

**Files:**
- Create: `app/services/quota.py`
- Create: `app/schemas/tasks.py`
- Create: `app/routers/tasks.py`
- Test: `tests/integration/test_tasks_crud.py`

- [ ] **Step 1: Test (RED)**

`tests/integration/test_tasks_crud.py`:

```python
from sqlalchemy import select
from app.db import session_scope
from app.models import User


async def _make_verified_user(client, email: str = "tu@x.dev") -> None:
    await client.post("/api/v1/auth/register", json={"email": email, "password": "passw0rd!"})
    async with session_scope() as s:
        u = (await s.execute(select(User).where(User.email == email))).scalar_one()
        u.email_verified = True
        await s.commit()
    await client.post("/api/v1/auth/login", json={"email": email, "password": "passw0rd!"})


async def test_create_task(client):
    await _make_verified_user(client)
    r = await client.post("/api/v1/tasks", json={
        "name": "LLM agents",
        "arxiv_categories": ["cs.AI", "cs.LG"],
        "keywords": ["LLM agent", "tool use"],
        "interest_description": None,
    })
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "LLM agents"
    assert "rss_token" in data
    assert len(data["rss_token"]) >= 32


async def test_quota_blocks_third_task(client):
    await _make_verified_user(client)
    for i in range(2):
        r = await client.post("/api/v1/tasks", json={"name": f"t{i}", "arxiv_categories": ["cs.AI"]})
        assert r.status_code == 201
    r3 = await client.post("/api/v1/tasks", json={"name": "t3", "arxiv_categories": ["cs.AI"]})
    assert r3.status_code == 403


async def test_list_only_own_tasks(client):
    await _make_verified_user(client, "owner@x.dev")
    await client.post("/api/v1/tasks", json={"name": "mine", "arxiv_categories": ["cs.AI"]})
    # logout, login as another user
    await client.post("/api/v1/auth/logout")
    await _make_verified_user(client, "other@x.dev")
    r = await client.get("/api/v1/tasks")
    assert r.status_code == 200
    names = [t["name"] for t in r.json()]
    assert "mine" not in names


async def test_unverified_cannot_create(client):
    await client.post("/api/v1/auth/register", json={"email": "uv@x.dev", "password": "passw0rd!"})
    await client.post("/api/v1/auth/login", json={"email": "uv@x.dev", "password": "passw0rd!"})
    r = await client.post("/api/v1/tasks", json={"name": "x", "arxiv_categories": ["cs.AI"]})
    assert r.status_code == 403


async def test_regenerate_rss_token(client):
    await _make_verified_user(client)
    r = await client.post("/api/v1/tasks", json={"name": "t", "arxiv_categories": ["cs.AI"]})
    tid = r.json()["id"]
    old = r.json()["rss_token"]
    r2 = await client.post(f"/api/v1/tasks/{tid}/regenerate-rss-token")
    assert r2.status_code == 200
    assert r2.json()["rss_token"] != old
```

- [ ] **Step 2: app/services/quota.py**

```python
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Task, TaskQuota


async def get_or_create_quota(s: AsyncSession, user_id: int) -> TaskQuota:
    result = await s.execute(select(TaskQuota).where(TaskQuota.user_id == user_id))
    q = result.scalar_one_or_none()
    if q is None:
        q = TaskQuota(user_id=user_id, max_tasks=2)
        s.add(q)
        await s.flush()
    return q


async def can_add_task(s: AsyncSession, user_id: int) -> tuple[bool, str]:
    q = await get_or_create_quota(s, user_id)
    count = (await s.execute(
        select(func.count()).select_from(Task).where(Task.user_id == user_id)
    )).scalar_one()
    if count < q.max_tasks:
        return True, ""
    return False, f"Already at limit ({q.max_tasks}). Buy credits to extend."
```

- [ ] **Step 3: app/schemas/tasks.py**

```python
from datetime import datetime
from pydantic import BaseModel, Field, field_validator


class TaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    arxiv_categories: list[str] = Field(min_length=1)
    keywords: list[str] | None = None
    min_keyword_match: int = 1
    interest_description: str | None = Field(default=None, max_length=1000)
    max_papers_per_day: int = Field(default=10, ge=1, le=50)
    delivery_time: str = Field(default="08:00", pattern=r"^\d{2}:\d{2}$")
    delivery_channels: list[str] = Field(default_factory=lambda: ["email"])

    @field_validator("delivery_channels")
    @classmethod
    def _validate_channels(cls, v: list[str]) -> list[str]:
        allowed = {"email", "rss"}
        if not set(v).issubset(allowed):
            raise ValueError(f"channels must be subset of {allowed}")
        return v


class TaskUpdate(BaseModel):
    name: str | None = None
    arxiv_categories: list[str] | None = None
    keywords: list[str] | None = None
    min_keyword_match: int | None = None
    interest_description: str | None = None
    max_papers_per_day: int | None = None
    delivery_time: str | None = None
    delivery_channels: list[str] | None = None
    enabled: bool | None = None


class TaskOut(BaseModel):
    id: int
    name: str
    arxiv_categories: list[str]
    keywords: list[str] | None
    min_keyword_match: int
    interest_description: str | None
    max_papers_per_day: int
    delivery_time: str
    delivery_channels: list[str]
    rss_token: str
    enabled: bool
    created_at: datetime
    updated_at: datetime
```

- [ ] **Step 4: app/routers/tasks.py**

```python
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.db import session_scope
from app.deps import require_email_verified
from app.models import Task, User
from app.schemas.tasks import TaskCreate, TaskOut, TaskUpdate
from app.services.quota import can_add_task
from app.services.tokens import random_token

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


@router.get("", response_model=list[TaskOut])
async def list_tasks(user: Annotated[User, Depends(require_email_verified)]):
    async with session_scope() as s:
        result = await s.execute(select(Task).where(Task.user_id == user.id))
        return [TaskOut.model_validate(t, from_attributes=True) for t in result.scalars()]


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def create_task(payload: TaskCreate, user: Annotated[User, Depends(require_email_verified)]):
    async with session_scope() as s:
        ok, reason = await can_add_task(s, user.id)
        if not ok:
            raise HTTPException(status.HTTP_403_FORBIDDEN, reason)
        task = Task(
            user_id=user.id,
            name=payload.name,
            arxiv_categories=payload.arxiv_categories,
            keywords=payload.keywords,
            min_keyword_match=payload.min_keyword_match,
            interest_description=payload.interest_description,
            max_papers_per_day=payload.max_papers_per_day,
            delivery_time=payload.delivery_time,
            delivery_channels=payload.delivery_channels,
            rss_token=random_token(32),
            enabled=True,
        )
        s.add(task)
        await s.commit()
        await s.refresh(task)
        return TaskOut.model_validate(task, from_attributes=True)


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(task_id: int, user: Annotated[User, Depends(require_email_verified)]):
    async with session_scope() as s:
        t = (await s.execute(select(Task).where(Task.id == task_id, Task.user_id == user.id))).scalar_one_or_none()
        if not t:
            raise HTTPException(status.HTTP_404_NOT_FOUND)
        return TaskOut.model_validate(t, from_attributes=True)


@router.patch("/{task_id}", response_model=TaskOut)
async def update_task(task_id: int, payload: TaskUpdate, user: Annotated[User, Depends(require_email_verified)]):
    async with session_scope() as s:
        t = (await s.execute(select(Task).where(Task.id == task_id, Task.user_id == user.id))).scalar_one_or_none()
        if not t:
            raise HTTPException(status.HTTP_404_NOT_FOUND)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(t, field, value)
        await s.commit()
        await s.refresh(t)
        return TaskOut.model_validate(t, from_attributes=True)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: int, user: Annotated[User, Depends(require_email_verified)]):
    async with session_scope() as s:
        t = (await s.execute(select(Task).where(Task.id == task_id, Task.user_id == user.id))).scalar_one_or_none()
        if not t:
            raise HTTPException(status.HTTP_404_NOT_FOUND)
        await s.delete(t)
        await s.commit()


@router.post("/{task_id}/regenerate-rss-token", response_model=TaskOut)
async def regen_rss(task_id: int, user: Annotated[User, Depends(require_email_verified)]):
    async with session_scope() as s:
        t = (await s.execute(select(Task).where(Task.id == task_id, Task.user_id == user.id))).scalar_one_or_none()
        if not t:
            raise HTTPException(status.HTTP_404_NOT_FOUND)
        t.rss_token = random_token(32)
        await s.commit()
        await s.refresh(t)
        return TaskOut.model_validate(t, from_attributes=True)
```

Mount in `app/main.py`.

- [ ] **Step 5: Run tests + commit**

```bash
uv run pytest tests/integration/test_tasks_crud.py -v
git add app/services/quota.py app/schemas/tasks.py app/routers/tasks.py app/main.py tests/
git commit -m "feat: tasks: add Task CRUD with quota check (max 2 per user)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 09: Tasks Dashboard UI

**Files:**
- Create: `templates/dashboard/index.html`
- Create: `templates/dashboard/task_form.html`
- Modify: `app/routers/pages.py` (dashboard routes)
- Test: `tests/integration/test_pages_dashboard.py`

- [ ] **Step 1: Test (RED)**

```python
async def test_dashboard_requires_login(client):
    r = await client.get("/dashboard", follow_redirects=False)
    assert r.status_code in (302, 303)


async def test_dashboard_lists_user_tasks(client):
    # register, verify, login, create task, GET /dashboard
    ...
    r = await client.get("/dashboard")
    assert r.status_code == 200
    assert "LLM agents" in r.text
```

- [ ] **Step 2: Templates**

`templates/dashboard/index.html`:
```html
{% extends "base.html" %}
{% block content %}
<h1 class="text-2xl font-semibold mb-6">Dashboard</h1>
<section class="mb-8">
  <div class="flex justify-between items-center mb-3">
    <h2 class="text-lg font-medium">Your tasks ({{ tasks|length }}/{{ max_tasks }})</h2>
    {% if tasks|length < max_tasks %}
      <a href="/dashboard/tasks/new" class="bg-zinc-900 text-white px-3 py-1.5 rounded text-sm">New task</a>
    {% endif %}
  </div>
  {% if not tasks %}<p class="text-zinc-500">No tasks yet. Create one to start receiving daily arXiv digests.</p>{% endif %}
  <ul class="space-y-3">
  {% for t in tasks %}
    <li class="border rounded p-4 bg-white">
      <div class="flex justify-between">
        <h3 class="font-medium">{{ t.name }}</h3>
        <span class="text-xs text-zinc-500">{{ t.delivery_time }} ({{ t.arxiv_categories|join(', ') }})</span>
      </div>
      {% if t.keywords %}<p class="text-sm text-zinc-600">keywords: {{ t.keywords|join(', ') }}</p>{% endif %}
      <div class="text-xs text-zinc-500 mt-2">
        RSS: <code class="bg-zinc-100 px-1 rounded">{{ base_url }}/rss/{{ user.id }}/{{ t.id }}/feed.xml?token={{ t.rss_token }}</code>
      </div>
      <div class="mt-3 space-x-2 text-sm">
        <a href="/dashboard/tasks/{{ t.id }}" class="underline">Edit</a>
      </div>
    </li>
  {% endfor %}
  </ul>
</section>
<section>
  <h2 class="text-lg font-medium mb-2">Your prompts</h2>
  <a href="/dashboard/prompts" class="text-sm underline">View all</a>
</section>
{% endblock %}
```

`templates/dashboard/task_form.html` — form for create/edit (similar pattern, posts to `/dashboard/tasks` or `/dashboard/tasks/{id}`).

- [ ] **Step 3: Pages router**

```python
from app.deps import current_user
from app.models import Task

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None):
    user = await _try_user(session)
    if not user:
        return RedirectResponse("/login", status_code=303)
    async with session_scope() as s:
        tasks = (await s.execute(select(Task).where(Task.user_id == user.id))).scalars().all()
    return templates.TemplateResponse("dashboard/index.html", {
        "request": request, "user": user, "tasks": tasks,
        "max_tasks": 2,
        "base_url": get_settings().app_base_url,
    })


@router.get("/dashboard/tasks/new", response_class=HTMLResponse)
async def new_task_page(request: Request, session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None):
    user = await _try_user(session)
    if not user:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse("dashboard/task_form.html", {
        "request": request, "user": user, "task": None,
    })


# Post handler delegates to API + redirects
```

- [ ] **Step 4: Run tests + commit**

```bash
uv run pytest tests/integration/test_pages_dashboard.py -v
git add templates/dashboard/ app/routers/pages.py tests/
git commit -m "feat: pages: add dashboard with task list + create form

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: arXiv Fetcher Service

**Files:**
- Create: `app/services/arxiv_fetcher.py`
- Create: `tests/fixtures/arxiv_response.xml`
- Test: `tests/unit/test_arxiv_fetcher.py`

- [ ] **Step 1: Capture sample arXiv API response**

Save a real arXiv API response to `tests/fixtures/arxiv_response.xml`. Use this as the canonical fixture. Example URL: `http://export.arxiv.org/api/query?search_query=cat:cs.AI&start=0&max_results=5&sortBy=submittedDate&sortOrder=descending`.

- [ ] **Step 2: Test (RED)**

`tests/unit/test_arxiv_fetcher.py`:

```python
from pathlib import Path
from app.services.arxiv_fetcher import parse_feed, ArxivPaper


def test_parse_fixture_returns_papers():
    xml = (Path(__file__).parent.parent / "fixtures" / "arxiv_response.xml").read_text()
    papers = parse_feed(xml)
    assert len(papers) >= 1
    p = papers[0]
    assert isinstance(p, ArxivPaper)
    assert p.id.startswith("")  # arxiv id format e.g. "2401.12345"
    assert p.title
    assert p.abstract
    assert isinstance(p.authors, list)
    assert p.primary_category
```

- [ ] **Step 3: Implementation**

```python
import asyncio
from dataclasses import dataclass
from datetime import datetime

import httpx
import feedparser

ARXIV_API = "http://export.arxiv.org/api/query"
RATE_LIMIT_SECONDS = 3.5  # arXiv rate limit


@dataclass
class ArxivPaper:
    id: str
    title: str
    abstract: str
    authors: list[str]
    primary_category: str
    all_categories: list[str]
    published_at: datetime | None
    pdf_url: str | None


def parse_feed(xml: str) -> list[ArxivPaper]:
    feed = feedparser.parse(xml)
    out: list[ArxivPaper] = []
    for entry in feed.entries:
        # arxiv id is the trailing path segment of entry.id like http://arxiv.org/abs/2401.12345v1
        raw_id = entry.id.rsplit("/", 1)[-1]
        clean_id = raw_id.split("v")[0]  # strip version
        cats = [t["term"] for t in entry.get("tags", [])]
        primary = (entry.get("arxiv_primary_category") or {}).get("term") or (cats[0] if cats else "")
        pdf = next((l.href for l in entry.get("links", []) if l.get("type") == "application/pdf"), None)
        published = None
        if "published_parsed" in entry:
            published = datetime(*entry.published_parsed[:6])
        out.append(ArxivPaper(
            id=clean_id,
            title=entry.title.strip().replace("\n", " "),
            abstract=entry.summary.strip(),
            authors=[a.name for a in entry.get("authors", [])],
            primary_category=primary,
            all_categories=cats,
            published_at=published,
            pdf_url=pdf,
        ))
    return out


async def fetch_recent(categories: list[str], max_results: int = 200) -> list[ArxivPaper]:
    """Fetch recent papers in given categories. Rate-limited to comply with arxiv ToS."""
    query = " OR ".join(f"cat:{c}" for c in categories)
    params = {
        "search_query": query,
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        for attempt in range(3):
            try:
                r = await client.get(ARXIV_API, params=params)
                r.raise_for_status()
                await asyncio.sleep(RATE_LIMIT_SECONDS)
                return parse_feed(r.text)
            except httpx.HTTPError:
                if attempt == 2:
                    raise
                await asyncio.sleep(2 ** attempt)
    return []
```

- [ ] **Step 4: Run tests + commit**

```bash
uv run pytest tests/unit/test_arxiv_fetcher.py -v
git add app/services/arxiv_fetcher.py tests/
git commit -m "feat: arxiv: add fetcher service with rate-limited API client and feed parser

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: Embedding Service

**Files:**
- Create: `app/services/embedding.py`
- Create: `tests/fixtures/embedding_seed.py`
- Test: `tests/unit/test_embedding.py`

- [ ] **Step 1: Test (RED)**

`tests/unit/test_embedding.py`:

```python
from app.services.embedding import embed_text, EMBEDDING_DIM


async def test_mock_embedding_is_deterministic():
    a = await embed_text("hello world")
    b = await embed_text("hello world")
    assert a == b
    assert len(a) == EMBEDDING_DIM


async def test_different_text_different_embedding():
    a = await embed_text("hello world")
    b = await embed_text("goodbye world")
    assert a != b
```

- [ ] **Step 2: Implementation**

```python
import hashlib
import struct
from typing import Protocol

from app.config import get_settings

EMBEDDING_DIM = 1536


class EmbeddingBackend(Protocol):
    async def embed(self, text: str) -> list[float]: ...


class MockBackend:
    """Deterministic seedable embedding for tests."""
    @staticmethod
    async def embed(text: str) -> list[float]:
        digest = hashlib.sha256(text.encode()).digest()
        # Expand the 32-byte digest into 1536 floats deterministically
        floats: list[float] = []
        for i in range(EMBEDDING_DIM):
            chunk_idx = (i * 4) % 32
            chunk = digest[chunk_idx:chunk_idx + 4]
            if len(chunk) < 4:
                chunk = (chunk + digest[:4])[:4]
            (val,) = struct.unpack("<I", chunk)
            # Mix with index for variation
            floats.append(((val + i * 17) % 10000) / 10000.0 - 0.5)
        # L2 normalize
        norm = sum(f * f for f in floats) ** 0.5 or 1.0
        return [f / norm for f in floats]


class OpenAIBackend:
    async def embed(self, text: str) -> list[float]:
        from openai import AsyncOpenAI
        settings = get_settings()
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        r = await client.embeddings.create(model=settings.embedding_model, input=text)
        return r.data[0].embedding


def get_backend() -> EmbeddingBackend:
    provider = get_settings().embedding_provider
    if provider == "openai":
        return OpenAIBackend()
    return MockBackend()


async def embed_text(text: str) -> list[float]:
    return await get_backend().embed(text)


def to_blob(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def from_blob(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))
```

- [ ] **Step 3: Run tests + commit**

```bash
uv run pytest tests/unit/test_embedding.py -v
git add app/services/embedding.py tests/
git commit -m "feat: embedding: add provider-agnostic embedding service with mock backend

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: arXiv Daily Fetch Cron + cron_runs Logging

**Files:**
- Create: `app/services/cron_log.py`
- Create: `app/jobs/__init__.py`
- Create: `app/jobs/fetch_arxiv.py`
- Test: `tests/integration/test_fetch_arxiv_job.py`

- [ ] **Step 1: app/services/cron_log.py**

```python
from contextlib import asynccontextmanager
from datetime import datetime
from app.db import session_scope
from app.models import CronRun


@asynccontextmanager
async def cron_run(job_name: str):
    """Wrap a cron job execution with cron_runs row tracking."""
    async with session_scope() as s:
        run = CronRun(job_name=job_name, started_at=datetime.utcnow(), status="running", job_metadata={})
        s.add(run)
        await s.commit()
        run_id = run.id
    metadata: dict = {}
    try:
        yield metadata
    except Exception as exc:
        async with session_scope() as s:
            r = await s.get(CronRun, run_id)
            r.ended_at = datetime.utcnow()
            r.status = "failed"
            r.error_message = str(exc)[:500]
            r.job_metadata = metadata
            await s.commit()
        raise
    else:
        async with session_scope() as s:
            r = await s.get(CronRun, run_id)
            r.ended_at = datetime.utcnow()
            r.status = "success"
            r.job_metadata = metadata
            await s.commit()
```

- [ ] **Step 2: app/jobs/fetch_arxiv.py**

```python
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.config import get_settings
from app.db import session_scope, engine
from app.models import Paper
from app.services.arxiv_fetcher import fetch_recent
from app.services.cron_log import cron_run
from app.services.embedding import embed_text, to_blob


async def run_fetch_arxiv() -> None:
    async with cron_run("fetch_arxiv") as meta:
        cats = get_settings().arxiv_category_list
        papers = await fetch_recent(cats, max_results=300)
        meta["fetched"] = len(papers)
        new_count = 0
        async with session_scope() as s:
            for p in papers:
                stmt = sqlite_insert(Paper).values(
                    id=p.id, title=p.title, abstract=p.abstract,
                    authors=p.authors, primary_category=p.primary_category,
                    all_categories=p.all_categories,
                    published_at=p.published_at, pdf_url=p.pdf_url,
                ).on_conflict_do_nothing(index_elements=["id"])
                result = await s.execute(stmt)
                if result.rowcount:
                    new_count += 1
            await s.commit()

        # Embed new papers
        embedded = 0
        async with session_scope() as s:
            # Find papers without vectors
            sql = """SELECT p.id, p.title, p.abstract FROM papers p
                     LEFT JOIN paper_vectors pv ON pv.paper_id = p.id
                     WHERE pv.paper_id IS NULL LIMIT 300"""
            result = await s.execute(__import__("sqlalchemy").text(sql))
            for row in result:
                pid, title, abstract = row
                vec = await embed_text(f"{title}\n\n{abstract}")
                blob = to_blob(vec)
                await s.execute(
                    __import__("sqlalchemy").text(
                        "INSERT INTO paper_vectors(paper_id, embedding) VALUES (:pid, :emb)"
                    ),
                    {"pid": pid, "emb": blob},
                )
                embedded += 1
            await s.commit()
        meta["new_papers"] = new_count
        meta["embedded"] = embedded
```

- [ ] **Step 3: Test**

`tests/integration/test_fetch_arxiv_job.py`:

```python
from unittest.mock import patch
from app.jobs.fetch_arxiv import run_fetch_arxiv
from app.db import session_scope
from app.models import Paper, CronRun
from sqlalchemy import select


async def _fake_papers():
    from app.services.arxiv_fetcher import ArxivPaper
    from datetime import datetime
    return [
        ArxivPaper(id="2401.00001", title="T1", abstract="A1", authors=["X"],
                   primary_category="cs.AI", all_categories=["cs.AI"], published_at=datetime.utcnow(), pdf_url=None),
        ArxivPaper(id="2401.00002", title="T2", abstract="A2", authors=["Y"],
                   primary_category="cs.LG", all_categories=["cs.LG"], published_at=datetime.utcnow(), pdf_url=None),
    ]


async def test_fetch_arxiv_persists_and_logs():
    with patch("app.jobs.fetch_arxiv.fetch_recent", return_value=_fake_papers()):
        await run_fetch_arxiv()
    async with session_scope() as s:
        papers = (await s.execute(select(Paper))).scalars().all()
        assert len(papers) >= 2
        runs = (await s.execute(select(CronRun).where(CronRun.job_name == "fetch_arxiv"))).scalars().all()
        assert len(runs) == 1
        assert runs[0].status == "success"
        assert runs[0].job_metadata.get("new_papers", 0) >= 2
```

- [ ] **Step 4: Run tests + commit**

```bash
uv run pytest tests/integration/test_fetch_arxiv_job.py -v
git add app/services/cron_log.py app/jobs/ tests/
git commit -m "feat: jobs: add fetch_arxiv cron job with embedding + cron_runs logging

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 13: Digest Filter Pipeline

**Files:**
- Create: `app/services/digest.py`
- Test: `tests/unit/test_digest_filter.py`

- [ ] **Step 1: Test (RED)**

```python
async def test_keyword_filter_includes_matching():
    # Create paper with title containing "RAG"; create task with keywords=["RAG"]; expect match
    ...

async def test_min_keyword_match_enforced():
    # task min_keyword_match=2; paper has only 1 keyword; expect not matched
    ...

async def test_semantic_rerank_orders_by_similarity():
    # 3 papers, task description embed; expect top result closest to description
    ...

async def test_max_papers_per_day_limits():
    # 20 candidates, max_papers_per_day=5, expect 5 returned
    ...
```

(Full test bodies in plan execution; key behaviors: each Stage 1-4 of pipeline.)

- [ ] **Step 2: Implementation**

```python
from datetime import datetime, timedelta
from typing import Sequence

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Paper, Task, Delivery, TaskEmbedding
from app.services.embedding import embed_text, to_blob, from_blob


async def candidates_for_task(s: AsyncSession, task: Task, *, since_hours: int = 36) -> list[Paper]:
    cutoff = datetime.utcnow() - timedelta(hours=since_hours)
    rows = await s.execute(
        select(Paper).where(
            Paper.primary_category.in_(task.arxiv_categories),
            Paper.published_at >= cutoff,
        )
    )
    return list(rows.scalars())


def keyword_match(paper: Paper, task: Task) -> int:
    if not task.keywords:
        return 0
    text_lower = (paper.title + " " + paper.abstract).lower()
    return sum(1 for k in task.keywords if k.lower() in text_lower)


async def get_or_compute_task_embedding(s: AsyncSession, task: Task) -> list[float] | None:
    if not task.interest_description:
        return None
    existing = await s.get(TaskEmbedding, task.id)
    if existing and existing.source_text == task.interest_description:
        return from_blob(existing.embedding)
    vec = await embed_text(task.interest_description)
    if existing:
        existing.embedding = to_blob(vec)
        existing.source_text = task.interest_description
    else:
        s.add(TaskEmbedding(task_id=task.id, embedding=to_blob(vec), source_text=task.interest_description))
    await s.commit()
    return vec


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


async def get_paper_embedding(s: AsyncSession, paper_id: str) -> list[float] | None:
    row = await s.execute(text("SELECT embedding FROM paper_vectors WHERE paper_id = :p"), {"p": paper_id})
    r = row.first()
    if not r:
        return None
    return from_blob(r[0])


async def select_papers_for_task(s: AsyncSession, task: Task) -> list[Paper]:
    cands = await candidates_for_task(s, task)
    if task.keywords:
        cands = [p for p in cands if keyword_match(p, task) >= task.min_keyword_match]
    task_vec = await get_or_compute_task_embedding(s, task)
    if task_vec:
        scored: list[tuple[float, Paper]] = []
        for p in cands:
            pv = await get_paper_embedding(s, p.id)
            if pv:
                scored.append((cosine(task_vec, pv), p))
            else:
                scored.append((0.0, p))
        scored.sort(key=lambda x: -x[0])
        cands = [p for _, p in scored]
    # Already-delivered filter
    delivered_ids = set((await s.execute(
        select(Delivery.paper_id).where(Delivery.task_id == task.id, Delivery.channel == "email")
    )).scalars())
    cands = [p for p in cands if p.id not in delivered_ids]
    return cands[: task.max_papers_per_day]
```

- [ ] **Step 3: Run tests + commit**

```bash
uv run pytest tests/unit/test_digest_filter.py -v
git add app/services/digest.py tests/
git commit -m "feat: digest: add filter pipeline (category/keyword/semantic/dedup/topN)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 14: Email Rendering + Send Digest

**Files:**
- Create: `templates/emails/digest.html`
- Create: `templates/emails/digest.txt`
- Modify: `app/services/digest.py` (render + send)
- Test: `tests/unit/test_digest_rendering.py`

- [ ] **Step 1: Email templates**

`templates/emails/digest.html`:
```html
<!doctype html>
<html><body style="font-family:-apple-system,BlinkMacSystemFont,sans-serif;color:#222;">
<h2 style="margin:0 0 12px;">🧪 {{ task.name }} · arXiv 早报 · {{ today }}</h2>
<p style="color:#666;font-size:13px;">{{ papers|length }} new papers matched.</p>
{% for p in papers %}
<article style="border-top:1px solid #eee;padding:12px 0;">
  <h3 style="margin:0 0 4px;font-size:16px;"><a href="https://arxiv.org/abs/{{ p.id }}" style="color:#1a56db;">{{ p.title }}</a></h3>
  <p style="margin:0 0 4px;color:#888;font-size:12px;">{{ p.authors[:3]|join(', ') }}{% if p.authors|length > 3 %} et al.{% endif %} · {{ p.primary_category }}</p>
  <p style="margin:0;font-size:14px;">{{ p.abstract[:600] }}{% if p.abstract|length > 600 %}…{% endif %}</p>
  <p style="margin:6px 0 0;font-size:12px;"><a href="{{ p.pdf_url or 'https://arxiv.org/pdf/' + p.id }}" style="color:#1a56db;">PDF →</a></p>
</article>
{% endfor %}
<p style="color:#aaa;font-size:11px;margin-top:24px;">xivLab · <a href="{{ unsubscribe_url }}" style="color:#aaa;">manage subscription</a></p>
</body></html>
```

`templates/emails/digest.txt`: plain-text version.

- [ ] **Step 2: Append to app/services/digest.py**

```python
from datetime import date
from jinja2 import Environment, FileSystemLoader
from app.config import PROJECT_ROOT, get_settings
from app.services.email import send_email

_jinja_email = Environment(loader=FileSystemLoader(str(PROJECT_ROOT / "templates" / "emails")))


def render_digest(task: Task, papers: list[Paper], unsubscribe_url: str) -> tuple[str, str]:
    ctx = {"task": task, "papers": papers, "today": date.today().isoformat(), "unsubscribe_url": unsubscribe_url}
    return (
        _jinja_email.get_template("digest.html").render(**ctx),
        _jinja_email.get_template("digest.txt").render(**ctx),
    )


async def deliver_email(s: AsyncSession, user, task: Task, papers: list[Paper]) -> None:
    if not papers:
        return
    settings = get_settings()
    unsub = f"{settings.app_base_url}/dashboard/tasks/{task.id}"
    html, text = render_digest(task, papers, unsub)
    await send_email(
        to=user.email,
        subject=f"🧪 {task.name} · {len(papers)} papers · {date.today().isoformat()}",
        html=html, text=text,
    )
    for p in papers:
        s.add(Delivery(user_id=user.id, task_id=task.id, paper_id=p.id, channel="email"))
    await s.commit()
```

- [ ] **Step 3: Test rendering doesn't crash**

`tests/unit/test_digest_rendering.py`:

```python
from app.services.digest import render_digest
from app.models import Task, Paper


def test_render_digest_includes_titles():
    t = Task(name="X", arxiv_categories=["cs.AI"], rss_token="x")
    p = Paper(id="2401.00001", title="My Title", abstract="Abstract " * 50,
              authors=["A", "B", "C", "D"], primary_category="cs.AI", all_categories=["cs.AI"])
    html, text = render_digest(t, [p], "http://x/u")
    assert "My Title" in html
    assert "et al." in html
    assert "My Title" in text
```

- [ ] **Step 4: Run tests + commit**

```bash
uv run pytest tests/unit/test_digest_rendering.py -v
git add templates/emails/ app/services/digest.py tests/
git commit -m "feat: digest: render email templates and deliver via email backend

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 15: send_digests Cron Job

**Files:**
- Create: `app/jobs/send_digests.py`
- Test: `tests/integration/test_send_digests_job.py`

- [ ] **Step 1: Implementation**

```python
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from app.db import session_scope
from app.models import User, Task
from app.services.cron_log import cron_run
from app.services.digest import select_papers_for_task, deliver_email


async def run_send_digests() -> None:
    async with cron_run("send_digests") as meta:
        now_utc = datetime.utcnow().replace(second=0, microsecond=0)
        digests_sent = 0
        async with session_scope() as s:
            users = (await s.execute(select(User).where(User.email_verified.is_(True)))).scalars().all()
            for user in users:
                try:
                    tz = ZoneInfo(user.tz)
                except Exception:
                    tz = ZoneInfo("UTC")
                local = now_utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz)
                hh_mm = local.strftime("%H:%M")
                tasks = (await s.execute(
                    select(Task).where(
                        Task.user_id == user.id,
                        Task.enabled.is_(True),
                        Task.delivery_time == hh_mm,
                    )
                )).scalars().all()
                for task in tasks:
                    if "email" not in (task.delivery_channels or []):
                        continue
                    papers = await select_papers_for_task(s, task)
                    if papers:
                        await deliver_email(s, user, task, papers)
                        digests_sent += 1
        meta["digests_sent"] = digests_sent
```

- [ ] **Step 2: Test (mocking time)**

`tests/integration/test_send_digests_job.py`:

```python
from datetime import datetime
from unittest.mock import patch
from app.jobs.send_digests import run_send_digests
from app.services.email import MockEmailBackend
# create user with tz, task with delivery_time matching mocked "now", paper matching keywords
# run; assert MockEmailBackend.sent has the email
```

- [ ] **Step 3: Run tests + commit**

```bash
uv run pytest tests/integration/test_send_digests_job.py -v
git add app/jobs/send_digests.py tests/
git commit -m "feat: jobs: add send_digests cron with per-user TZ matching and dedup

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 16: RSS Feed Renderer + Endpoint

**Files:**
- Create: `app/services/feed_renderer.py`
- Create: `app/routers/rss.py`
- Test: `tests/integration/test_rss.py`

- [ ] **Step 1: Test (RED)**

```python
async def test_rss_feed_requires_token(client):
    # create user/task; GET without token → 403/404
    ...

async def test_rss_feed_returns_atom(client):
    # with correct token → status 200, xml header, contains paper IDs
    ...
```

- [ ] **Step 2: Implementation**

```python
# app/services/feed_renderer.py
from datetime import datetime
from xml.sax.saxutils import escape
from app.models import Task, Paper


def render_atom(task: Task, papers: list[Paper], base_url: str, user_id: int) -> str:
    feed_url = f"{base_url}/rss/{user_id}/{task.id}/feed.xml?token={task.rss_token}"
    updated = datetime.utcnow().isoformat() + "Z"
    entries = []
    for p in papers:
        entries.append(f"""
  <entry>
    <id>https://arxiv.org/abs/{p.id}</id>
    <title>{escape(p.title)}</title>
    <updated>{p.published_at.isoformat() if p.published_at else updated}Z</updated>
    <author><name>{escape(', '.join(p.authors[:3]))}</name></author>
    <link href="https://arxiv.org/abs/{p.id}"/>
    <summary type="html">{escape(p.abstract[:1000])}</summary>
    <category term="{p.primary_category}"/>
  </entry>""")
    return f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <id>{feed_url}</id>
  <title>{escape(task.name)} · xivLab arXiv 早报</title>
  <updated>{updated}</updated>
  <link href="{feed_url}" rel="self"/>
  {''.join(entries)}
</feed>"""
```

```python
# app/routers/rss.py
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from app.config import get_settings
from app.db import session_scope
from app.models import Task, Paper, Delivery
from app.services.feed_renderer import render_atom

router = APIRouter()


@router.get("/rss/{user_id}/{task_id}/feed.xml")
async def task_feed(user_id: int, task_id: int, token: str):
    async with session_scope() as s:
        task = (await s.execute(select(Task).where(Task.id == task_id, Task.user_id == user_id))).scalar_one_or_none()
        if not task or task.rss_token != token:
            raise HTTPException(status.HTTP_404_NOT_FOUND)
        # Most recent 30 days of deliveries OR all candidate papers (fallback)
        cutoff = datetime.utcnow() - timedelta(days=30)
        rows = await s.execute(
            select(Paper)
            .join(Delivery, Delivery.paper_id == Paper.id)
            .where(Delivery.task_id == task.id, Delivery.delivered_at >= cutoff)
            .order_by(Paper.published_at.desc())
            .limit(50)
        )
        papers = list(rows.scalars())
    xml = render_atom(task, papers, get_settings().app_base_url, user_id)
    return Response(content=xml, media_type="application/atom+xml")
```

- [ ] **Step 3: Run tests + commit**

```bash
uv run pytest tests/integration/test_rss.py -v
git add app/services/feed_renderer.py app/routers/rss.py app/main.py tests/
git commit -m "feat: rss: add Atom feed endpoint with token auth

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 17: Prompts CRUD API + Spam Guards

**Files:**
- Create: `app/services/slug.py`
- Create: `app/schemas/prompts.py`
- Create: `app/routers/prompts.py`
- Test: `tests/integration/test_prompts_crud.py`

- [ ] **Step 1: app/services/slug.py**

```python
import re


def slugify(text: str, max_len: int = 80) -> str:
    s = text.lower().strip()
    s = re.sub(r"[^a-z0-9一-鿿]+", "-", s)  # allow CJK
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:max_len] or "prompt"
```

- [ ] **Step 2: schemas + router covering POST/GET/PATCH/DELETE/vote/copy-track/view-track**

(Standard CRUD pattern; spam guards: count `prompts.created_at` for current user today, reject if >= 5; reject if title > 100 / body > 5000.)

- [ ] **Step 3: Tests covering: create requires verified email, daily 5-prompt limit, vote idempotency, copy-track 30s anti-spam, list filters by category/sort/lang/q, only published in public list, author can edit own**

- [ ] **Step 4: Run + commit**

```bash
uv run pytest tests/integration/test_prompts_crud.py -v
git add app/services/slug.py app/schemas/prompts.py app/routers/prompts.py app/main.py tests/
git commit -m "feat: prompts: CRUD API with daily limit, voting, copy/view tracking

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 18: Categories Endpoint + Public List

**Files:**
- Create: `app/routers/categories.py`
- Test: `tests/integration/test_categories.py`

- [ ] **Step 1: Categories list endpoint**

```python
@router.get("/api/v1/categories")
async def list_categories():
    async with session_scope() as s:
        rows = (await s.execute(select(PromptCategory).order_by(PromptCategory.sort_order))).scalars().all()
        return [{"slug": c.slug, "name": c.name, "description": c.description, "icon": c.icon} for c in rows]
```

- [ ] **Step 2: Test + commit**

---

## Task 19: PromptHub Frontend — Home + Category Page

**Files:**
- Create: `templates/pages/home.html`
- Create: `templates/pages/category.html`
- Modify: `app/routers/pages.py`
- Test: `tests/integration/test_pages_prompts.py`

- [ ] **Step 1: Home renders 9 categories × top 5 published prompts**
- [ ] **Step 2: Category page renders all published prompts in that category, sortable by hot/new**
- [ ] **Step 3: Tests + commit**

(Implementation follows the standard pages pattern from earlier Tasks.)

---

## Task 20: PromptHub Frontend — Detail + Create Form

**Files:**
- Create: `templates/pages/prompt_detail.html`
- Create: `templates/pages/prompt_form.html`
- Create: `templates/dashboard/prompts.html`
- Modify: `app/routers/pages.py`
- Test: `tests/integration/test_pages_prompts.py`

Detail page includes: copy button (HTMX hits `/api/v1/prompts/{id}/copy-track`), vote button (HTMX `/vote`), view tracking on page load.

Create form uses a simple `<textarea>` for body (skip Monaco editor in MVP — can add via Alpine integration later).

`/dashboard/prompts` lists user's own prompts with status badges (pending/published/rejected) and review_note when rejected.

- [ ] Tests + commit.

---

## Task 21: Admin Queue + Approve/Reject

**Files:**
- Create: `app/routers/admin.py`
- Create: `templates/admin/queue.html`
- Modify: `app/routers/pages.py` (admin queue page)
- Test: `tests/integration/test_admin_queue.py`

- [ ] **Step 1: API endpoints**

```python
# /api/v1/admin/pending-prompts → list status='pending'
# /api/v1/admin/prompts/{id}/approve → set status='published'
# /api/v1/admin/prompts/{id}/reject → set status='rejected', save review_note
```

- [ ] **Step 2: Admin queue UI with approve/reject HTMX actions**

- [ ] **Step 3: Tests: only admin can access; approve flips status; reject saves note; non-admin gets 403**

- [ ] **Step 4: Commit**

---

## Task 22: APScheduler Wiring + /health Endpoint

**Files:**
- Create: `app/scheduler.py`
- Create: `app/routers/health.py`
- Modify: `app/main.py` (lifespan starts/stops scheduler)
- Test: `tests/integration/test_scheduler.py`
- Test: `tests/integration/test_health.py`

- [ ] **Step 1: app/scheduler.py**

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from app.jobs.fetch_arxiv import run_fetch_arxiv
from app.jobs.send_digests import run_send_digests

scheduler = AsyncIOScheduler(timezone="UTC")


def register_jobs() -> None:
    scheduler.add_job(run_fetch_arxiv, CronTrigger(hour=2, minute=0), id="fetch_arxiv", replace_existing=True)
    scheduler.add_job(run_send_digests, CronTrigger(minute="*"), id="send_digests", replace_existing=True)
    # Refresh RSS, backup, cleanup tasks added in next Task
```

- [ ] **Step 2: Lifespan in app/main.py**

```python
from contextlib import asynccontextmanager
from app.scheduler import scheduler, register_jobs


@asynccontextmanager
async def lifespan(app):
    register_jobs()
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


def create_app() -> FastAPI:
    app = FastAPI(..., lifespan=lifespan)
    ...
```

- [ ] **Step 3: /health endpoint**

```python
@router.get("/health")
async def health():
    async with session_scope() as s:
        await s.execute(text("SELECT 1"))
    last_arxiv = (await s.execute(select(CronRun).where(CronRun.job_name == "fetch_arxiv").order_by(CronRun.started_at.desc()).limit(1))).scalar_one_or_none()
    return {"status": "ok", "db": "ok", "last_arxiv_run": last_arxiv.started_at if last_arxiv else None}
```

- [ ] **Step 4: Tests + commit**

---

## Task 23: Backup + Cleanup Cron Jobs

**Files:**
- Create: `app/jobs/backup.py`
- Create: `app/jobs/cleanup.py`
- Modify: `app/scheduler.py`
- Test: `tests/integration/test_backup_cleanup.py`

- [ ] **Step 1: backup.py — runs `sqlite3 .backup` via subprocess; rotate to 14 days**
- [ ] **Step 2: cleanup.py — DELETE expired sessions, used tokens, old cron_runs (>30 days)**
- [ ] **Step 3: Register in scheduler at 04:00 / 04:30 UTC**
- [ ] **Step 4: refresh_rss job — write per-task feeds to disk under `data/rss_cache/`**
- [ ] **Step 5: Tests + commit**

---

## Task 24: scripts/create_admin.py + scripts/check_health.py

**Files:**
- Create: `scripts/create_admin.py`
- Create: `scripts/check_health.py`

- [ ] **Step 1: create_admin.py — interactive prompt for email/password, hashes, sets is_admin=True, email_verified=True**

- [ ] **Step 2: check_health.py — calls `/health`, exits non-zero if unhealthy**

- [ ] **Step 3: Commit**

---

## Task 25: Deployment Artifacts

**Files:**
- Create: `deploy/xivlab.service`
- Create: `deploy/nginx.conf`
- Create: `deploy/deploy.sh`

- [ ] **Step 1: Copy systemd unit from spec §6.2**
- [ ] **Step 2: Copy nginx config from spec §6.3**
- [ ] **Step 3: deploy.sh — `rsync` source to Sacurajima, run `uv sync`, `alembic upgrade head`, `systemctl restart xivlab`**
- [ ] **Step 4: Update README with deploy instructions**
- [ ] **Step 5: Commit**

---

## Task 26: E2E Smoke Test + Polish

**Files:**
- Create: `tests/integration/test_smoke_e2e.py`

- [ ] **Step 1: End-to-end test:**
  1. Register
  2. Verify email (manually fish token from DB)
  3. Login
  4. Create task with keywords + interest_description
  5. Trigger fetch_arxiv (mocked papers)
  6. Trigger send_digests (mocked time)
  7. Assert email sent (MockEmailBackend)
  8. GET /rss/.../feed.xml with token → assert 200 + valid XML
  9. Create prompt → admin login → approve → assert appears on home page
  10. Logout

- [ ] **Step 2: Run full suite**

```bash
uv run pytest -v
uv run ruff check app/ tests/
uv run pyright app/
```

All green.

- [ ] **Step 3: Final commit**

```bash
git commit -m "test: add full e2e smoke test covering register→digest→rss→prompt flow

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 27: README Polish + CHANGELOG.md

**Files:**
- Modify: `README.md`
- Create: `CHANGELOG.md`

- [ ] **Step 1: README sections — Quickstart, Development, Deployment, Architecture link to spec**
- [ ] **Step 2: CHANGELOG.md with v0.1.0 release notes pointing to MVP feature set**
- [ ] **Step 3: Commit**

---

## Task 28: Final Deploy + Tag

**Files:**
- (none)

- [ ] **Step 1: SSH to Sacurajima**
- [ ] **Step 2: Run `deploy/deploy.sh`**
- [ ] **Step 3: Run `scripts/check_health.py` against production URL**
- [ ] **Step 4: Tag v0.1.0**
  ```bash
  git tag -a v0.1.0 -m "MVP release: arXiv 早报 + PromptHub"
  git push origin v0.1.0
  ```
- [ ] **Step 5: Manual smoke check via browser:** register, verify, create task, see dashboard, view RSS URL.

---

## Done When

- All 28 Tasks committed on `main`
- `uv run pytest` exits 0
- `uv run ruff check app/ tests/` exits 0
- `uv run pyright app/` exits 0
- `https://xivlab.<your-domain>/health` returns `{"status": "ok"}`
- A registered + verified user can create a task, receive a (mocked-content) digest email, and access RSS feed
- A user can create a prompt, admin can approve it, and it appears on the home page
- systemd `MemoryMax=500M` not breached during cron runs (check `systemctl status xivlab`)
