"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-05-04 19:14:42.686084

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "cron_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_name", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("job_metadata", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("cron_runs", schema=None) as batch_op:
        batch_op.create_index("idx_cron_runs_job_started", ["job_name", "started_at"], unique=False)

    op.create_table(
        "papers",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("abstract", sa.Text(), nullable=False),
        sa.Column("authors", sa.JSON(), nullable=False),
        sa.Column("primary_category", sa.String(length=32), nullable=True),
        sa.Column("all_categories", sa.JSON(), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("pdf_url", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("papers", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_papers_primary_category"), ["primary_category"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_papers_published_at"), ["published_at"], unique=False)

    op.create_table(
        "prompt_categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("icon", sa.String(length=64), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("email_verified", sa.Boolean(), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=True),
        sa.Column("tz", sa.String(length=64), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_users_email"), ["email"], unique=True)

    op.create_table(
        "credit_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=False),
        sa.Column("ref_type", sa.String(length=64), nullable=True),
        sa.Column("ref_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("credit_events", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_credit_events_user_id"), ["user_id"], unique=False)

    op.create_table(
        "email_verification_tokens",
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("token"),
    )

    op.create_table(
        "password_reset_tokens",
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("token"),
    )

    op.create_table(
        "prompts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("variables", sa.JSON(), nullable=True),
        sa.Column("example_input", sa.Text(), nullable=True),
        sa.Column("example_output", sa.Text(), nullable=True),
        sa.Column("author_user_id", sa.Integer(), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("upvotes", sa.Integer(), nullable=False),
        sa.Column("copies", sa.Integer(), nullable=False),
        sa.Column("views", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("forked_from_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["category_id"], ["prompt_categories.id"]),
        sa.ForeignKeyConstraint(["forked_from_id"], ["prompts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    with op.batch_alter_table("prompts", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_prompts_author_user_id"), ["author_user_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_prompts_category_id"), ["category_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_prompts_status"), ["status"], unique=False)

    op.create_table(
        "sessions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("sessions", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_sessions_user_id"), ["user_id"], unique=False)

    op.create_table(
        "task_quotas",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("max_tasks", sa.Integer(), nullable=False),
        sa.Column("last_recalc", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )

    op.create_table(
        "tasks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("arxiv_categories", sa.JSON(), nullable=False),
        sa.Column("keywords", sa.JSON(), nullable=True),
        sa.Column("min_keyword_match", sa.Integer(), nullable=False),
        sa.Column("interest_description", sa.Text(), nullable=True),
        sa.Column("max_papers_per_day", sa.Integer(), nullable=False),
        sa.Column("delivery_time", sa.String(length=5), nullable=False),
        sa.Column("delivery_channels", sa.JSON(), nullable=False),
        sa.Column("rss_token", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rss_token"),
    )
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_tasks_user_id"), ["user_id"], unique=False)

    op.create_table(
        "user_credits",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("balance", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )

    op.create_table(
        "deliveries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("paper_id", sa.String(length=64), nullable=False),
        sa.Column("delivered_at", sa.DateTime(), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("opened_at", sa.DateTime(), nullable=True),
        sa.Column("clicked_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "task_id", "paper_id", "channel", name="uq_deliveries_task_paper_channel"
        ),
    )
    with op.batch_alter_table("deliveries", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_deliveries_task_id"), ["task_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_deliveries_user_id"), ["user_id"], unique=False)

    op.create_table(
        "prompt_copy_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("prompt_id", sa.Integer(), nullable=False),
        sa.Column("user_or_ip", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["prompt_id"], ["prompts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("prompt_copy_events", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_prompt_copy_events_prompt_id"), ["prompt_id"], unique=False
        )

    op.create_table(
        "prompt_votes",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("prompt_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["prompt_id"], ["prompts.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("user_id", "prompt_id"),
    )

    op.create_table(
        "task_embeddings",
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("embedding", sa.LargeBinary(), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("embedded_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("task_id"),
    )

    # sqlite-vec virtual table for paper embeddings (1536-dim, OpenAI text-embedding-3-small).
    # Autogen does not detect virtual tables; created here via raw DDL.
    op.execute(
        """
        CREATE VIRTUAL TABLE paper_vectors USING vec0(
            paper_id TEXT PRIMARY KEY,
            embedding FLOAT[1536]
        );
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TABLE IF EXISTS paper_vectors;")

    op.drop_table("task_embeddings")
    op.drop_table("prompt_votes")
    with op.batch_alter_table("prompt_copy_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_prompt_copy_events_prompt_id"))
    op.drop_table("prompt_copy_events")
    with op.batch_alter_table("deliveries", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_deliveries_user_id"))
        batch_op.drop_index(batch_op.f("ix_deliveries_task_id"))
    op.drop_table("deliveries")
    op.drop_table("user_credits")
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_tasks_user_id"))
    op.drop_table("tasks")
    op.drop_table("task_quotas")
    with op.batch_alter_table("sessions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_sessions_user_id"))
    op.drop_table("sessions")
    with op.batch_alter_table("prompts", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_prompts_status"))
        batch_op.drop_index(batch_op.f("ix_prompts_category_id"))
        batch_op.drop_index(batch_op.f("ix_prompts_author_user_id"))
    op.drop_table("prompts")
    op.drop_table("password_reset_tokens")
    op.drop_table("email_verification_tokens")
    with op.batch_alter_table("credit_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_credit_events_user_id"))
    op.drop_table("credit_events")
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_users_email"))
    op.drop_table("users")
    op.drop_table("prompt_categories")
    with op.batch_alter_table("papers", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_papers_published_at"))
        batch_op.drop_index(batch_op.f("ix_papers_primary_category"))
    op.drop_table("papers")
    with op.batch_alter_table("cron_runs", schema=None) as batch_op:
        batch_op.drop_index("idx_cron_runs_job_started")
    op.drop_table("cron_runs")
