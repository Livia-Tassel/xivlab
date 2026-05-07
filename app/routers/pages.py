"""Server-rendered HTML pages backed by Jinja2 + HTMX.

The pages here orchestrate the auth services directly (rather than calling
the JSON API endpoints) so that error rendering, redirects, and cookies
are all idiomatic FastAPI ``Response`` constructions.
"""

from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Cookie, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from app.config import PROJECT_ROOT, get_settings
from app.db import session_scope
from app.deps import COOKIE_NAME, current_user
from app.models import (
    EmailVerificationToken,
    PasswordResetToken,
    Prompt,
    PromptCategory,
    Task,
    User,
)
from app.schemas.tasks import TaskCreate, TaskUpdate
from app.services.email import send_email
from app.services.password import hash_password, verify_password
from app.services.quota import DEFAULT_MAX_TASKS, can_add_task, get_or_create_quota
from app.services.session import SESSION_LIFETIME, create_session
from app.services.tokens import random_token

templates = Jinja2Templates(directory=str(PROJECT_ROOT / "templates"))
router = APIRouter()

VERIFY_TOKEN_LIFETIME = timedelta(hours=48)
PASSWORD_RESET_LIFETIME = timedelta(hours=48)


async def _try_user(session_token: str | None) -> User | None:
    """Best-effort: return the User for a session cookie, or None if missing/expired."""
    if not session_token:
        return None
    try:
        return await current_user(session=session_token)
    except Exception:  # expected: HTTPException(401) from current_user
        return None


# --- Login -----------------------------------------------------------------


@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> Response:
    user = await _try_user(session)
    return templates.TemplateResponse(request, "auth/login.html", {"user": user})


@router.post("/login")
async def login_submit(
    request: Request,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
) -> Response:
    async with session_scope() as s:
        user = (await s.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if user is None or not verify_password(password, user.password_hash):
            return templates.TemplateResponse(
                request,
                "auth/login.html",
                {"user": None, "error": "Bad credentials"},
                status_code=401,
            )
        sess = await create_session(
            s,
            user,
            user_agent=request.headers.get("user-agent"),
            ip=request.client.host if request.client is not None else None,
        )

    redirect = RedirectResponse("/dashboard", status_code=303)
    redirect.set_cookie(
        COOKIE_NAME,
        sess.id,
        httponly=True,
        samesite="lax",
        secure=False,  # TODO flip in prod via APP_ENV
        max_age=int(SESSION_LIFETIME.total_seconds()),
    )
    return redirect


# --- Register --------------------------------------------------------------


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request) -> Response:
    return templates.TemplateResponse(request, "auth/register.html", {"user": None})


@router.post("/register")
async def register_submit(
    request: Request,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    display_name: Annotated[str | None, Form()] = None,
) -> Response:
    if len(password) < 8:
        return templates.TemplateResponse(
            request,
            "auth/register.html",
            {"user": None, "error": "Password must be at least 8 characters"},
            status_code=422,
        )

    display_name_clean = (display_name or "").strip() or None

    async with session_scope() as s:
        existing = (await s.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if existing is not None:
            return templates.TemplateResponse(
                request,
                "auth/register.html",
                {"user": None, "error": "Email already registered"},
                status_code=409,
            )
        user = User(
            email=email,
            password_hash=hash_password(password),
            display_name=display_name_clean,
        )
        s.add(user)
        await s.flush()
        token_value = random_token(32)
        s.add(
            EmailVerificationToken(
                token=token_value,
                user_id=user.id,
                expires_at=datetime.utcnow() + VERIFY_TOKEN_LIFETIME,
            )
        )
        await s.commit()

    settings = get_settings()
    verify_url = f"{settings.app_base_url}/verify-email/{token_value}"
    await send_email(
        to=email,
        subject="[xivLab] Verify your email",
        html=(
            "<p>Welcome to xivLab! Confirm your email by clicking: "
            f'<a href="{verify_url}">{verify_url}</a></p>'
        ),
        text=f"Welcome to xivLab! Confirm your email: {verify_url}",
    )

    return RedirectResponse(f"/verify-pending?email={email}", status_code=303)


@router.get("/verify-pending", response_class=HTMLResponse)
async def verify_pending_page(request: Request, email: str | None = None) -> Response:
    return templates.TemplateResponse(
        request, "auth/verify_pending.html", {"user": None, "email": email}
    )


# --- Email verification (link landing) -------------------------------------


@router.get("/verify-email/{token}", response_class=HTMLResponse)
async def verify_email_page(request: Request, token: str) -> Response:
    """Landing page for the verification link in the user's inbox.

    Consumes the token immediately on GET — same one-shot semantics as the
    JSON API. Renders a success or failure page accordingly.
    """
    ok = False
    async with session_scope() as s:
        evt = (
            await s.execute(
                select(EmailVerificationToken).where(EmailVerificationToken.token == token)
            )
        ).scalar_one_or_none()
        if evt is not None and evt.used_at is None and evt.expires_at >= datetime.utcnow():
            user = (await s.execute(select(User).where(User.id == evt.user_id))).scalar_one()
            user.email_verified = True
            evt.used_at = datetime.utcnow()
            await s.commit()
            ok = True
    return templates.TemplateResponse(
        request,
        "auth/verify_result.html",
        {"user": None, "ok": ok},
        status_code=200 if ok else 410,
    )


# --- Forgot / reset password -----------------------------------------------


@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request) -> Response:
    return templates.TemplateResponse(
        request, "auth/forgot_password.html", {"user": None, "sent": False}
    )


@router.post("/forgot-password")
async def forgot_password_submit(request: Request, email: Annotated[str, Form()]) -> Response:
    token_value: str | None = None
    user_email: str | None = None
    async with session_scope() as s:
        user = (await s.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if user is not None:
            token_value = random_token(32)
            s.add(
                PasswordResetToken(
                    token=token_value,
                    user_id=user.id,
                    expires_at=datetime.utcnow() + PASSWORD_RESET_LIFETIME,
                )
            )
            await s.commit()
            user_email = user.email

    if token_value is not None and user_email is not None:
        settings = get_settings()
        url = f"{settings.app_base_url}/reset-password/{token_value}"
        await send_email(
            to=user_email,
            subject="[xivLab] Reset your password",
            html=(
                "<p>Click the link to reset your password: "
                f'<a href="{url}">{url}</a>. '
                "This link expires in 48 hours.</p>"
            ),
            text=f"Click the link to reset your password: {url}\nThis link expires in 48 hours.",
        )

    return templates.TemplateResponse(
        request, "auth/forgot_password.html", {"user": None, "sent": True}
    )


@router.get("/reset-password/{token}", response_class=HTMLResponse)
async def reset_password_page(request: Request, token: str) -> Response:
    return templates.TemplateResponse(
        request,
        "auth/reset_password.html",
        {"user": None, "token": token, "done": False},
    )


@router.post("/reset-password")
async def reset_password_submit(
    request: Request,
    token: Annotated[str, Form()],
    new_password: Annotated[str, Form()],
) -> Response:
    if len(new_password) < 8:
        return templates.TemplateResponse(
            request,
            "auth/reset_password.html",
            {
                "user": None,
                "token": token,
                "done": False,
                "error": "Password must be at least 8 characters",
            },
            status_code=422,
        )

    async with session_scope() as s:
        tok = (
            await s.execute(select(PasswordResetToken).where(PasswordResetToken.token == token))
        ).scalar_one_or_none()
        if tok is None or tok.used_at is not None or tok.expires_at < datetime.utcnow():
            return templates.TemplateResponse(
                request,
                "auth/reset_password.html",
                {
                    "user": None,
                    "token": token,
                    "done": False,
                    "error": "Invalid or expired token",
                },
                status_code=404,
            )
        user = (await s.execute(select(User).where(User.id == tok.user_id))).scalar_one()
        user.password_hash = hash_password(new_password)
        tok.used_at = datetime.utcnow()
        await s.commit()

    return templates.TemplateResponse(
        request, "auth/reset_password.html", {"user": None, "token": token, "done": True}
    )


# --- Dashboard -------------------------------------------------------------


def _split_csv(raw: str | None) -> list[str]:
    """Split a comma-separated form value, drop blanks, trim whitespace."""
    if not raw:
        return []
    return [piece.strip() for piece in raw.split(",") if piece.strip()]


def _form_dict_from_request(
    name: str,
    arxiv_categories: str,
    keywords: str,
    interest_description: str,
    min_keyword_match: int,
    max_papers_per_day: int,
    delivery_time: str,
    delivery_channels: list[str],
) -> dict[str, object]:
    """Build the dict we pass back to the form template on validation errors."""
    return {
        "name": name,
        "arxiv_categories": arxiv_categories,
        "keywords": keywords,
        "interest_description": interest_description,
        "min_keyword_match": min_keyword_match,
        "max_papers_per_day": max_papers_per_day,
        "delivery_time": delivery_time,
        "delivery_channels": delivery_channels,
    }


async def _verified_user_or_redirect(
    session_token: str | None,
) -> tuple[User | None, Response | None]:
    """Resolve the verified user. Returns (user, None) on success, or
    (None, redirect_response) when the caller should bail out with a redirect.
    """
    user = await _try_user(session_token)
    if user is None:
        return None, RedirectResponse("/login", status_code=303)
    if not user.email_verified:
        return None, RedirectResponse(f"/verify-pending?email={user.email}", status_code=303)
    return user, None


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(
    request: Request,
    session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> Response:
    user, redirect = await _verified_user_or_redirect(session)
    if redirect is not None:
        return redirect
    assert user is not None
    async with session_scope() as s:
        tasks = list(
            (
                await s.execute(
                    select(Task).where(Task.user_id == user.id).order_by(Task.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
        quota = await get_or_create_quota(s, user.id)
        max_tasks = quota.max_tasks
        await s.commit()
    return templates.TemplateResponse(
        request,
        "dashboard/index.html",
        {
            "user": user,
            "tasks": tasks,
            "max_tasks": max_tasks,
            "base_url": get_settings().app_base_url,
        },
    )


@router.get("/dashboard/tasks/new", response_class=HTMLResponse)
async def new_task_page(
    request: Request,
    session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> Response:
    user, redirect = await _verified_user_or_redirect(session)
    if redirect is not None:
        return redirect
    return templates.TemplateResponse(
        request,
        "dashboard/task_form.html",
        {"user": user, "task": None, "form": None},
    )


@router.post("/dashboard/tasks")
async def create_task_submit(
    request: Request,
    name: Annotated[str, Form()],
    arxiv_categories: Annotated[str, Form()],
    keywords: Annotated[str, Form()] = "",
    interest_description: Annotated[str, Form()] = "",
    min_keyword_match: Annotated[int, Form()] = 1,
    max_papers_per_day: Annotated[int, Form()] = 10,
    delivery_time: Annotated[str, Form()] = "08:00",
    delivery_channels: Annotated[list[str] | None, Form()] = None,
    session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> Response:
    user, redirect = await _verified_user_or_redirect(session)
    if redirect is not None:
        return redirect
    assert user is not None

    channels = delivery_channels or ["email"]
    form = _form_dict_from_request(
        name,
        arxiv_categories,
        keywords,
        interest_description,
        min_keyword_match,
        max_papers_per_day,
        delivery_time,
        channels,
    )

    try:
        payload = TaskCreate(
            name=name,
            arxiv_categories=_split_csv(arxiv_categories),
            keywords=_split_csv(keywords) or None,
            min_keyword_match=min_keyword_match,
            interest_description=interest_description.strip() or None,
            max_papers_per_day=max_papers_per_day,
            delivery_time=delivery_time,
            delivery_channels=channels,
        )
    except ValueError as exc:
        return templates.TemplateResponse(
            request,
            "dashboard/task_form.html",
            {"user": user, "task": None, "form": form, "error": str(exc)},
            status_code=422,
        )

    async with session_scope() as s:
        ok, reason = await can_add_task(s, user.id)
        if not ok:
            return templates.TemplateResponse(
                request,
                "dashboard/task_form.html",
                {"user": user, "task": None, "form": form, "error": reason},
                status_code=403,
            )
        s.add(
            Task(
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
        )
        await s.commit()

    return RedirectResponse("/dashboard", status_code=303)


@router.get("/dashboard/tasks/{task_id}", response_class=HTMLResponse)
async def edit_task_page(
    request: Request,
    task_id: int,
    session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> Response:
    user, redirect = await _verified_user_or_redirect(session)
    if redirect is not None:
        return redirect
    assert user is not None
    async with session_scope() as s:
        task = (
            await s.execute(select(Task).where(Task.id == task_id, Task.user_id == user.id))
        ).scalar_one_or_none()
        if task is None:
            return Response(status_code=404, content="Not found")
    return templates.TemplateResponse(
        request,
        "dashboard/task_form.html",
        {"user": user, "task": task, "form": None},
    )


@router.post("/dashboard/tasks/{task_id}")
async def update_task_submit(
    request: Request,
    task_id: int,
    name: Annotated[str, Form()],
    arxiv_categories: Annotated[str, Form()],
    keywords: Annotated[str, Form()] = "",
    interest_description: Annotated[str, Form()] = "",
    min_keyword_match: Annotated[int, Form()] = 1,
    max_papers_per_day: Annotated[int, Form()] = 10,
    delivery_time: Annotated[str, Form()] = "08:00",
    delivery_channels: Annotated[list[str] | None, Form()] = None,
    enabled: Annotated[bool, Form()] = True,
    session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> Response:
    user, redirect = await _verified_user_or_redirect(session)
    if redirect is not None:
        return redirect
    assert user is not None

    channels = delivery_channels or ["email"]
    form = _form_dict_from_request(
        name,
        arxiv_categories,
        keywords,
        interest_description,
        min_keyword_match,
        max_papers_per_day,
        delivery_time,
        channels,
    )

    async with session_scope() as s:
        task = (
            await s.execute(select(Task).where(Task.id == task_id, Task.user_id == user.id))
        ).scalar_one_or_none()
        if task is None:
            return Response(status_code=404, content="Not found")

        try:
            payload = TaskUpdate(
                name=name,
                arxiv_categories=_split_csv(arxiv_categories),
                keywords=_split_csv(keywords) or None,
                min_keyword_match=min_keyword_match,
                interest_description=interest_description.strip() or None,
                max_papers_per_day=max_papers_per_day,
                delivery_time=delivery_time,
                delivery_channels=channels,
                enabled=enabled,
            )
        except ValueError as exc:
            return templates.TemplateResponse(
                request,
                "dashboard/task_form.html",
                {"user": user, "task": task, "form": form, "error": str(exc)},
                status_code=422,
            )

        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(task, field, value)
        await s.commit()

    return RedirectResponse("/dashboard", status_code=303)


@router.post("/dashboard/tasks/{task_id}/delete")
async def delete_task_submit(
    task_id: int,
    session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> Response:
    user, redirect = await _verified_user_or_redirect(session)
    if redirect is not None:
        return redirect
    assert user is not None
    async with session_scope() as s:
        task = (
            await s.execute(select(Task).where(Task.id == task_id, Task.user_id == user.id))
        ).scalar_one_or_none()
        if task is not None:
            await s.delete(task)
            await s.commit()
    return RedirectResponse("/dashboard", status_code=303)


@router.post("/dashboard/tasks/{task_id}/regenerate-rss-token")
async def regenerate_rss_submit(
    task_id: int,
    session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> Response:
    user, redirect = await _verified_user_or_redirect(session)
    if redirect is not None:
        return redirect
    assert user is not None
    async with session_scope() as s:
        task = (
            await s.execute(select(Task).where(Task.id == task_id, Task.user_id == user.id))
        ).scalar_one_or_none()
        if task is not None:
            task.rss_token = random_token(32)
            await s.commit()
    return RedirectResponse("/dashboard", status_code=303)


# --- PromptHub: home + category --------------------------------------------


HOME_PROMPTS_PER_CATEGORY: int = 5


@router.get("/", response_class=HTMLResponse)
async def home_page(
    request: Request,
    session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> Response:
    user = await _try_user(session)
    async with session_scope() as s:
        cats = list(
            (await s.execute(select(PromptCategory).order_by(PromptCategory.sort_order)))
            .scalars()
            .all()
        )
        groups: list[tuple[PromptCategory, list[Prompt]]] = []
        for cat in cats:
            prompts = list(
                (
                    await s.execute(
                        select(Prompt)
                        .where(
                            Prompt.category_id == cat.id,
                            Prompt.status == "published",
                        )
                        .order_by(Prompt.upvotes.desc(), Prompt.created_at.desc())
                        .limit(HOME_PROMPTS_PER_CATEGORY)
                    )
                )
                .scalars()
                .all()
            )
            groups.append((cat, prompts))
    return templates.TemplateResponse(
        request,
        "pages/home.html",
        {"user": user, "groups": groups},
    )


@router.get("/c/{slug}", response_class=HTMLResponse)
async def category_page(
    request: Request,
    slug: str,
    sort: str = "new",
    session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> Response:
    user = await _try_user(session)
    async with session_scope() as s:
        cat = (
            await s.execute(select(PromptCategory).where(PromptCategory.slug == slug))
        ).scalar_one_or_none()
        if cat is None:
            return Response(status_code=404, content="Category not found")
        stmt = select(Prompt).where(Prompt.category_id == cat.id, Prompt.status == "published")
        if sort == "hot":
            stmt = stmt.order_by(Prompt.upvotes.desc(), Prompt.created_at.desc())
        else:
            stmt = stmt.order_by(Prompt.created_at.desc())
        prompts = list((await s.execute(stmt)).scalars().all())
    return templates.TemplateResponse(
        request,
        "pages/category.html",
        {"user": user, "category": cat, "prompts": prompts, "sort": sort},
    )


# --- PromptHub: detail + author dashboard ----------------------------------


def _split_tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [t.strip() for t in raw.split(",") if t.strip()]


@router.get("/p/{slug}", response_class=HTMLResponse)
async def prompt_detail_page(
    request: Request,
    slug: str,
    session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> Response:
    user = await _try_user(session)
    async with session_scope() as s:
        row = (
            await s.execute(
                select(Prompt, PromptCategory)
                .join(PromptCategory, PromptCategory.id == Prompt.category_id)
                .where(Prompt.slug == slug)
            )
        ).one_or_none()
        if row is None:
            return Response(status_code=404, content="Prompt not found")
        prompt, category = row
        if prompt.status != "published" and (user is None or user.id != prompt.author_user_id):
            return Response(status_code=404, content="Prompt not found")
        prompt.views += 1
        await s.commit()
        await s.refresh(prompt)
    return templates.TemplateResponse(
        request,
        "pages/prompt_detail.html",
        {"user": user, "prompt": prompt, "category": category},
    )


@router.get("/dashboard/prompts", response_class=HTMLResponse)
async def my_prompts_page(
    request: Request,
    session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> Response:
    user, redirect = await _verified_user_or_redirect(session)
    if redirect is not None:
        return redirect
    assert user is not None
    async with session_scope() as s:
        prompts = list(
            (
                await s.execute(
                    select(Prompt)
                    .where(
                        Prompt.author_user_id == user.id,
                        Prompt.status != "deleted",
                    )
                    .order_by(Prompt.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
    return templates.TemplateResponse(
        request,
        "dashboard/prompts.html",
        {"user": user, "prompts": prompts},
    )


async def _all_categories() -> list[PromptCategory]:
    async with session_scope() as s:
        return list(
            (await s.execute(select(PromptCategory).order_by(PromptCategory.sort_order)))
            .scalars()
            .all()
        )


@router.get("/dashboard/prompts/new", response_class=HTMLResponse)
async def new_prompt_page(
    request: Request,
    session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> Response:
    user, redirect = await _verified_user_or_redirect(session)
    if redirect is not None:
        return redirect
    assert user is not None
    return templates.TemplateResponse(
        request,
        "pages/prompt_form.html",
        {
            "user": user,
            "prompt": None,
            "form": None,
            "categories": await _all_categories(),
        },
    )


def _form_dict(
    title: str,
    description: str,
    body: str,
    category_slug: str,
    tags: str,
    language: str,
    example_input: str,
    example_output: str,
) -> dict[str, str]:
    return {
        "title": title,
        "description": description,
        "body": body,
        "category_slug": category_slug,
        "tags": tags,
        "language": language,
        "example_input": example_input,
        "example_output": example_output,
    }


@router.post("/dashboard/prompts")
async def create_prompt_submit(
    request: Request,
    title: Annotated[str, Form()],
    body: Annotated[str, Form()],
    category_slug: Annotated[str, Form()],
    description: Annotated[str, Form()] = "",
    tags: Annotated[str, Form()] = "",
    language: Annotated[str, Form()] = "zh",
    example_input: Annotated[str, Form()] = "",
    example_output: Annotated[str, Form()] = "",
    session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> Response:
    user, redirect = await _verified_user_or_redirect(session)
    if redirect is not None:
        return redirect
    assert user is not None

    form = _form_dict(
        title, description, body, category_slug, tags, language, example_input, example_output
    )

    if len(title) > 200:
        return templates.TemplateResponse(
            request,
            "pages/prompt_form.html",
            {
                "user": user,
                "prompt": None,
                "form": form,
                "categories": await _all_categories(),
                "error": "Title must be 200 characters or fewer.",
            },
            status_code=422,
        )
    if len(body) > 5000:
        return templates.TemplateResponse(
            request,
            "pages/prompt_form.html",
            {
                "user": user,
                "prompt": None,
                "form": form,
                "categories": await _all_categories(),
                "error": "Body must be 5000 characters or fewer.",
            },
            status_code=422,
        )

    async with session_scope() as s:
        cat = (
            await s.execute(select(PromptCategory).where(PromptCategory.slug == category_slug))
        ).scalar_one_or_none()
        if cat is None:
            return templates.TemplateResponse(
                request,
                "pages/prompt_form.html",
                {
                    "user": user,
                    "prompt": None,
                    "form": form,
                    "categories": await _all_categories(),
                    "error": f"Unknown category: {category_slug}",
                },
                status_code=400,
            )

        # Daily limit of 5
        from app.routers.prompts import DAILY_PROMPT_LIMIT

        day_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        from sqlalchemy import func

        count_today = (
            await s.execute(
                select(func.count())
                .select_from(Prompt)
                .where(Prompt.author_user_id == user.id, Prompt.created_at >= day_start)
            )
        ).scalar_one()
        if count_today >= DAILY_PROMPT_LIMIT:
            return templates.TemplateResponse(
                request,
                "pages/prompt_form.html",
                {
                    "user": user,
                    "prompt": None,
                    "form": form,
                    "categories": await _all_categories(),
                    "error": f"Daily limit reached ({DAILY_PROMPT_LIMIT}/day).",
                },
                status_code=429,
            )

        from app.routers.prompts import _unique_slug
        from app.services.slug import slugify

        slug = await _unique_slug(s, slugify(title))
        s.add(
            Prompt(
                slug=slug,
                title=title,
                description=description.strip() or None,
                body=body,
                category_id=cat.id,
                tags=_split_tags(tags),
                example_input=example_input.strip() or None,
                example_output=example_output.strip() or None,
                author_user_id=user.id,
                language=language,
                status="pending",
            )
        )
        await s.commit()

    return RedirectResponse("/dashboard/prompts", status_code=303)


@router.get("/dashboard/prompts/{prompt_id}", response_class=HTMLResponse)
async def edit_prompt_page(
    request: Request,
    prompt_id: int,
    session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> Response:
    user, redirect = await _verified_user_or_redirect(session)
    if redirect is not None:
        return redirect
    assert user is not None
    async with session_scope() as s:
        row = (
            await s.execute(
                select(Prompt, PromptCategory.slug)
                .join(PromptCategory, PromptCategory.id == Prompt.category_id)
                .where(Prompt.id == prompt_id, Prompt.author_user_id == user.id)
            )
        ).one_or_none()
        if row is None:
            return Response(status_code=404, content="Not found")
        prompt, cat_slug = row
        # Pass a small shim with category_slug for the template's selected option.
        prompt.__dict__["category_slug"] = cat_slug
    return templates.TemplateResponse(
        request,
        "pages/prompt_form.html",
        {
            "user": user,
            "prompt": prompt,
            "form": None,
            "categories": await _all_categories(),
        },
    )


@router.post("/dashboard/prompts/{prompt_id}")
async def update_prompt_submit(
    request: Request,
    prompt_id: int,
    title: Annotated[str, Form()],
    body: Annotated[str, Form()],
    category_slug: Annotated[str, Form()],
    description: Annotated[str, Form()] = "",
    tags: Annotated[str, Form()] = "",
    language: Annotated[str, Form()] = "zh",
    example_input: Annotated[str, Form()] = "",
    example_output: Annotated[str, Form()] = "",
    session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> Response:
    user, redirect = await _verified_user_or_redirect(session)
    if redirect is not None:
        return redirect
    assert user is not None

    async with session_scope() as s:
        prompt = (
            await s.execute(
                select(Prompt).where(Prompt.id == prompt_id, Prompt.author_user_id == user.id)
            )
        ).scalar_one_or_none()
        if prompt is None:
            return Response(status_code=404, content="Not found")

        cat = (
            await s.execute(select(PromptCategory).where(PromptCategory.slug == category_slug))
        ).scalar_one_or_none()
        if cat is None:
            return Response(status_code=400, content="Unknown category")

        prompt.title = title
        prompt.description = description.strip() or None
        prompt.body = body
        prompt.category_id = cat.id
        prompt.tags = _split_tags(tags)
        prompt.language = language
        prompt.example_input = example_input.strip() or None
        prompt.example_output = example_output.strip() or None
        prompt.status = "pending"
        await s.commit()

    return RedirectResponse("/dashboard/prompts", status_code=303)


@router.post("/dashboard/prompts/{prompt_id}/delete")
async def delete_prompt_submit(
    prompt_id: int,
    session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> Response:
    user, redirect = await _verified_user_or_redirect(session)
    if redirect is not None:
        return redirect
    assert user is not None
    async with session_scope() as s:
        prompt = (
            await s.execute(
                select(Prompt).where(Prompt.id == prompt_id, Prompt.author_user_id == user.id)
            )
        ).scalar_one_or_none()
        if prompt is not None:
            prompt.status = "deleted"
            await s.commit()
    return RedirectResponse("/dashboard/prompts", status_code=303)


# --- Admin queue page ------------------------------------------------------


@router.get("/admin/queue", response_class=HTMLResponse)
async def admin_queue_page(
    request: Request,
    session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> Response:
    user = await _try_user(session)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not user.is_admin:
        return Response(status_code=403, content="Admin only")
    async with session_scope() as s:
        rows = (
            await s.execute(
                select(Prompt, PromptCategory.slug, User.email)
                .join(PromptCategory, PromptCategory.id == Prompt.category_id)
                .join(User, User.id == Prompt.author_user_id)
                .where(Prompt.status == "pending")
                .order_by(Prompt.created_at.asc())
            )
        ).all()
        prompts = [
            {
                "id": p.id,
                "title": p.title,
                "description": p.description,
                "body": p.body,
                "category_slug": cs,
                "language": p.language,
                "author_email": em,
            }
            for p, cs, em in rows
        ]
    return templates.TemplateResponse(
        request,
        "admin/queue.html",
        {"user": user, "prompts": prompts},
    )


# Compatibility shim — `DEFAULT_MAX_TASKS` is exported but the dashboard
# reads the per-user value via ``get_or_create_quota``. Re-export so module
# imports stay tidy.
__all__ = ["DEFAULT_MAX_TASKS", "router"]
