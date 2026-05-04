from datetime import datetime
from typing import Any

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
    # 'running' | 'success' | 'failed'
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    # Avoid name clash with SQLAlchemy's `metadata` attribute on Base.
    job_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON)
