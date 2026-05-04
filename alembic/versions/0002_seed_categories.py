"""seed prompt_categories

Revision ID: 0002_seed_categories
Revises: 0001_initial_schema
Create Date: 2026-05-04 19:14:42.686084

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_seed_categories"
down_revision: str | Sequence[str] | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (slug, name, description, icon, sort_order)
CATEGORIES: list[tuple[str, str, str, str, int]] = [
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
    """Seed the 9 prompt categories."""
    bind = op.get_bind()
    for slug, name, desc, icon, order in CATEGORIES:
        bind.exec_driver_sql(
            "INSERT INTO prompt_categories (slug, name, description, icon, sort_order) "
            "VALUES (?, ?, ?, ?, ?)",
            (slug, name, desc, icon, order),
        )


def downgrade() -> None:
    """Remove all seeded categories."""
    op.execute("DELETE FROM prompt_categories;")
