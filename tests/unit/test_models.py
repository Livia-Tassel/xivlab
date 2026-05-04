from sqlalchemy import select

from app.db import session_scope
from app.models import PromptCategory, User


async def test_create_user_persists() -> None:
    async with session_scope() as s:
        # Defensive cleanup in case a previous run left this row behind
        leftover = (
            await s.execute(select(User).where(User.email == "t@x.dev"))
        ).scalar_one_or_none()
        if leftover is not None:
            await s.delete(leftover)
            await s.commit()

        try:
            s.add(User(email="t@x.dev", password_hash="x", display_name="T"))
            await s.commit()
            user = (await s.execute(select(User).where(User.email == "t@x.dev"))).scalar_one()
            assert user.email == "t@x.dev"
            assert user.email_verified is False
            assert user.tz == "Asia/Shanghai"
            assert user.is_admin is False
        finally:
            row = (
                await s.execute(select(User).where(User.email == "t@x.dev"))
            ).scalar_one_or_none()
            if row is not None:
                await s.delete(row)
                await s.commit()


async def test_categories_seeded() -> None:
    async with session_scope() as s:
        cats = (await s.execute(select(PromptCategory))).scalars().all()
        assert len(cats) == 9
        slugs = {c.slug for c in cats}
        assert "paper-writing" in slugs
        assert "code" in slugs
        assert "misc" in slugs
