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


# paper_vectors is a sqlite-vec virtual table created via raw SQL in migration 0001.
