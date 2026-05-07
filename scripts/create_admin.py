#!/usr/bin/env python3
"""Interactive admin-creation CLI.

Usage::

    uv run python scripts/create_admin.py

Prompts for email + password, sets is_admin=True and email_verified=True
on the resulting User row. Idempotent: if the email already exists, the
existing user is promoted to admin (password is updated only if entered).
"""

from __future__ import annotations

import asyncio
import getpass
import sys

from sqlalchemy import select

from app.db import session_scope
from app.models import User
from app.services.password import hash_password


async def _upsert_admin(email: str, password: str | None) -> str:
    async with session_scope() as s:
        u = (await s.scalars(select(User).where(User.email == email))).one_or_none()
        if u is None:
            assert password is not None, "password is required for new users"
            u = User(
                email=email,
                password_hash=hash_password(password),
                email_verified=True,
                is_admin=True,
            )
            s.add(u)
            action = "created"
        else:
            u.email_verified = True
            u.is_admin = True
            if password:
                u.password_hash = hash_password(password)
            action = "updated"
        await s.commit()
        return action


async def main() -> int:
    email = input("Admin email: ").strip()
    if not email or "@" not in email:
        print("error: invalid email", file=sys.stderr)
        return 1

    pw = getpass.getpass("Password (leave blank to keep existing if user exists): ")
    if pw:
        confirm = getpass.getpass("Confirm: ")
        if pw != confirm:
            print("error: passwords don't match", file=sys.stderr)
            return 1
        if len(pw) < 8:
            print("error: password must be at least 8 characters", file=sys.stderr)
            return 1
    else:
        pw_arg: str | None = None

    pw_arg = pw if pw else None

    async with session_scope() as s:
        existing = (await s.scalars(select(User).where(User.email == email))).one_or_none()
    if existing is None and pw_arg is None:
        print("error: password is required to create a new user", file=sys.stderr)
        return 1

    action = await _upsert_admin(email, pw_arg)
    print(f"admin {action}: {email}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
