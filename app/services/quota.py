"""Per-user task slot quota.

Default: 2 free task slots per user. ``TaskQuota.max_tasks`` is bumpable
via the admin queue (T24) or paid credits (post-MVP).
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Task, TaskQuota

DEFAULT_MAX_TASKS = 2


async def get_or_create_quota(s: AsyncSession, user_id: int) -> TaskQuota:
    q = (
        await s.execute(select(TaskQuota).where(TaskQuota.user_id == user_id))
    ).scalar_one_or_none()
    if q is None:
        q = TaskQuota(user_id=user_id, max_tasks=DEFAULT_MAX_TASKS)
        s.add(q)
        await s.flush()
    return q


async def can_add_task(s: AsyncSession, user_id: int) -> tuple[bool, str]:
    """Return ``(allowed, reason)``. Reason is empty when allowed."""
    q = await get_or_create_quota(s, user_id)
    count = (
        await s.execute(select(func.count()).select_from(Task).where(Task.user_id == user_id))
    ).scalar_one()
    if count < q.max_tasks:
        return True, ""
    return False, f"Already at limit ({q.max_tasks}). Buy credits to extend."
