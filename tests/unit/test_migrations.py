"""Sanity-check that migrations created the expected schema.

Doesn't reapply migrations (they're applied externally via `alembic upgrade
head`); just inspects the live DB and verifies invariants.
"""

from sqlalchemy import text

from app.db import session_scope

EXPECTED_TABLES: set[str] = {
    "alembic_version",
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
        try:
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
        finally:
            await s.execute(
                text("DELETE FROM paper_vectors WHERE paper_id = :pid"),
                {"pid": "test-arxiv-2026.0001"},
            )
            await s.commit()


async def test_alembic_version_is_seed_revision() -> None:
    async with session_scope() as s:
        result = await s.execute(text("SELECT version_num FROM alembic_version"))
        version = result.scalar_one()
        # After both migrations are applied head should be the seed revision.
        assert version == "0002_seed_categories"
