from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.db import session_scope
from app.deps import require_email_verified
from app.models import Task, User
from app.schemas.tasks import TaskCreate, TaskOut, TaskUpdate
from app.services.quota import can_add_task
from app.services.tokens import random_token

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


@router.get("", response_model=list[TaskOut])
async def list_tasks(
    user: Annotated[User, Depends(require_email_verified)],
) -> list[TaskOut]:
    async with session_scope() as s:
        result = await s.execute(
            select(Task).where(Task.user_id == user.id).order_by(Task.created_at.desc())
        )
        return [TaskOut.model_validate(t) for t in result.scalars()]


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: TaskCreate,
    user: Annotated[User, Depends(require_email_verified)],
) -> TaskOut:
    async with session_scope() as s:
        ok, reason = await can_add_task(s, user.id)
        if not ok:
            raise HTTPException(status.HTTP_403_FORBIDDEN, reason)
        task = Task(
            user_id=user.id,
            name=payload.name,
            arxiv_categories=payload.arxiv_categories,
            keywords=payload.keywords,
            min_keyword_match=payload.min_keyword_match,
            interest_description=payload.interest_description,
            max_papers_per_day=payload.max_papers_per_day,
            delivery_time=payload.delivery_time,
            delivery_channels=payload.delivery_channels,
            rss_token=random_token(32),
            enabled=True,
        )
        s.add(task)
        await s.commit()
        await s.refresh(task)
        return TaskOut.model_validate(task)


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(
    task_id: int,
    user: Annotated[User, Depends(require_email_verified)],
) -> TaskOut:
    async with session_scope() as s:
        t = (
            await s.execute(select(Task).where(Task.id == task_id, Task.user_id == user.id))
        ).scalar_one_or_none()
        if t is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND)
        return TaskOut.model_validate(t)


@router.patch("/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: int,
    payload: TaskUpdate,
    user: Annotated[User, Depends(require_email_verified)],
) -> TaskOut:
    async with session_scope() as s:
        t = (
            await s.execute(select(Task).where(Task.id == task_id, Task.user_id == user.id))
        ).scalar_one_or_none()
        if t is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(t, field, value)
        await s.commit()
        await s.refresh(t)
        return TaskOut.model_validate(t)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: int,
    user: Annotated[User, Depends(require_email_verified)],
) -> None:
    async with session_scope() as s:
        t = (
            await s.execute(select(Task).where(Task.id == task_id, Task.user_id == user.id))
        ).scalar_one_or_none()
        if t is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND)
        await s.delete(t)
        await s.commit()


@router.post("/{task_id}/regenerate-rss-token", response_model=TaskOut)
async def regenerate_rss_token(
    task_id: int,
    user: Annotated[User, Depends(require_email_verified)],
) -> TaskOut:
    async with session_scope() as s:
        t = (
            await s.execute(select(Task).where(Task.id == task_id, Task.user_id == user.id))
        ).scalar_one_or_none()
        if t is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND)
        t.rss_token = random_token(32)
        await s.commit()
        await s.refresh(t)
        return TaskOut.model_validate(t)
