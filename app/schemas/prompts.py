"""Pydantic schemas for the Prompts API.

Length caps mirror the ORM column definitions (Prompt.title=200,
Prompt.body=Text but spam-capped at 5000, Prompt.description=500) and
match the validation in the router's create/update flows.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

_ALLOWED_SORTS: set[str] = {"new", "top"}
_ALLOWED_LANGS: set[str] = {"zh", "en"}


class PromptCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    body: str = Field(min_length=1, max_length=5000)
    category_slug: str = Field(min_length=1, max_length=64)
    tags: list[str] = Field(default_factory=list)
    variables: list[dict[str, Any]] | None = None
    example_input: str | None = Field(default=None, max_length=5000)
    example_output: str | None = Field(default=None, max_length=5000)
    language: str = Field(min_length=2, max_length=8)


class PromptUpdate(BaseModel):
    """Author-edit. Only set fields are applied (PATCH)."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    body: str | None = Field(default=None, min_length=1, max_length=5000)
    category_slug: str | None = Field(default=None, min_length=1, max_length=64)
    tags: list[str] | None = None
    variables: list[dict[str, Any]] | None = None
    example_input: str | None = Field(default=None, max_length=5000)
    example_output: str | None = Field(default=None, max_length=5000)
    language: str | None = Field(default=None, min_length=2, max_length=8)


class PromptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    title: str
    description: str | None
    body: str
    category_slug: str
    tags: list[str]
    variables: list[dict[str, Any]] | None
    example_input: str | None
    example_output: str | None
    language: str
    upvotes: int
    copies: int
    views: int
    status: str
    created_at: datetime
    updated_at: datetime
