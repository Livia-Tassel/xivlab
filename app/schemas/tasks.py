from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

_ALLOWED_CHANNELS: set[str] = {"email", "rss"}


class TaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    arxiv_categories: list[str] = Field(min_length=1)
    keywords: list[str] | None = None
    min_keyword_match: int = Field(default=1, ge=1)
    interest_description: str | None = Field(default=None, max_length=1000)
    max_papers_per_day: int = Field(default=10, ge=1, le=50)
    delivery_time: str = Field(default="08:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    delivery_channels: list[str] = Field(default_factory=lambda: ["email"])

    @field_validator("delivery_channels")
    @classmethod
    def _validate_channels(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("delivery_channels must not be empty")
        bad = set(v) - _ALLOWED_CHANNELS
        if bad:
            raise ValueError(
                f"unknown channels: {sorted(bad)}; allowed: {sorted(_ALLOWED_CHANNELS)}"
            )
        return v


class TaskUpdate(BaseModel):
    """All fields optional. Only set fields are applied (PATCH semantics)."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    arxiv_categories: list[str] | None = Field(default=None, min_length=1)
    keywords: list[str] | None = None
    min_keyword_match: int | None = Field(default=None, ge=1)
    interest_description: str | None = Field(default=None, max_length=1000)
    max_papers_per_day: int | None = Field(default=None, ge=1, le=50)
    delivery_time: str | None = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    delivery_channels: list[str] | None = None
    enabled: bool | None = None

    @field_validator("delivery_channels")
    @classmethod
    def _validate_channels(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        if not v:
            raise ValueError("delivery_channels must not be empty")
        bad = set(v) - _ALLOWED_CHANNELS
        if bad:
            raise ValueError(
                f"unknown channels: {sorted(bad)}; allowed: {sorted(_ALLOWED_CHANNELS)}"
            )
        return v


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
