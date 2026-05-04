"""Pytest fixtures shared across all tests.

The autouse ``_reset_db`` fixture wipes and recreates the schema before each
test (including the sqlite-vec virtual table) and re-seeds the 9 prompt
categories. This gives each test a clean DB without paying the cost of a
full alembic upgrade per test.
"""

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.db import Base, engine, session_scope
from app.main import app
from app.models import PromptCategory

# Mirror of alembic/versions/0002_seed_categories.py
_SEED_CATEGORIES: list[tuple[str, str, str, str, int]] = [
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


@pytest_asyncio.fixture(autouse=True)
async def _reset_db() -> AsyncIterator[None]:
    """Reset the database to a fresh post-migration state before each test."""
    async with engine.begin() as conn:
        # sqlite-vec virtual table isn't in Base.metadata; drop explicitly so
        # its helper tables are cleaned up by sqlite-vec before we recreate.
        await conn.execute(text("DROP TABLE IF EXISTS paper_vectors"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text(
                "CREATE VIRTUAL TABLE paper_vectors USING vec0("
                "paper_id TEXT PRIMARY KEY, embedding FLOAT[1536])"
            )
        )

    async with session_scope() as s:
        for slug, name, desc, icon, order in _SEED_CATEGORIES:
            s.add(
                PromptCategory(
                    slug=slug,
                    name=name,
                    description=desc,
                    icon=icon,
                    sort_order=order,
                )
            )
        await s.commit()

    yield


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
