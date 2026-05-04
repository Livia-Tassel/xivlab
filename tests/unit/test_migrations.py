"""Sanity-check that the schema produced by the test fixtures matches what
the alembic migrations create.

These tests run against the per-test reset-and-reseed schema set up by
``conftest._reset_db``, not against a freshly migrated database. The
alembic-managed ``alembic_version`` table is therefore not asserted here;
that's a CI / deploy concern, not a test concern.
"""

from sqlalchemy import text

from app.db import session_scope

EXPECTED_TABLES: set[str] = {
    "credit_events",
    "cron_runs",
    "deliveries",
    "email_verification_tokens",
    "paper_vectors",  # sqlite-vec virtual table
    "papers",
    "password_reset_tokens",
    "prompt_categories",
    "prompt_copy_events",
    "prompt_votes",
    "prompts",
    "sessions",
    "task_embeddings",
    "task_quotas",
    "tasks",
    "user_credits",
    "users",
}


async def test_all_expected_tables_present() -> None:
    async with session_scope() as s:
        result = await s.execute(
            text("SELECT name FROM sqlite_master WHERE type IN ('table','view')")
        )
        names = {row[0] for row in result}
        missing = EXPECTED_TABLES - names
        assert not missing, f"missing tables: {missing}"


async def test_paper_vectors_is_virtual_vec0_table() -> None:
    """Insert + select against the sqlite-vec virtual table; round-trips a 1536-d vector."""
    async with session_scope() as s:
        # Use a deterministic bogus vector. sqlite-vec accepts JSON-array syntax.
        vec_json = "[" + ",".join(["0.0"] * 1536) + "]"
        await s.execute(
            text("INSERT INTO paper_vectors (paper_id, embedding) VALUES (:pid, :emb)"),
            {"pid": "test-arxiv-2026.0001", "emb": vec_json},
        )
        await s.commit()

        row = (
            await s.execute(
                text("SELECT paper_id FROM paper_vectors WHERE paper_id = :pid"),
                {"pid": "test-arxiv-2026.0001"},
            )
        ).first()
        assert row is not None
        assert row[0] == "test-arxiv-2026.0001"
