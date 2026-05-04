from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
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
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class TaskEmbedding(Base):
    __tablename__ = "task_embeddings"
    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
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
