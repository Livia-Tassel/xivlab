from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import PROJECT_ROOT
from app.routers import admin as admin_router
from app.routers import auth as auth_router
from app.routers import categories as categories_router
from app.routers import health as health_router
from app.routers import me as me_router
from app.routers import pages as pages_router
from app.routers import prompts as prompts_router
from app.routers import rss as rss_router
from app.routers import tasks as tasks_router
from app.scheduler import register_jobs, scheduler


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    register_jobs()
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


def create_app(start_scheduler: bool = True) -> FastAPI:
    kwargs: dict[str, Any] = {
        "title": "xivLab",
        "description": "Research AI tools — arXiv digest + PromptHub",
        "version": "0.1.0",
    }
    if start_scheduler:
        kwargs["lifespan"] = lifespan
    app = FastAPI(**kwargs)

    app.mount(
        "/static",
        StaticFiles(directory=str(PROJECT_ROOT / "static")),
        name="static",
    )
    app.include_router(health_router.router)
    app.include_router(auth_router.router)
    app.include_router(me_router.router)
    app.include_router(tasks_router.router)
    app.include_router(prompts_router.router)
    app.include_router(categories_router.router)
    app.include_router(admin_router.router)
    app.include_router(rss_router.router)
    app.include_router(pages_router.router)
    return app


# Production app — scheduler is wired via lifespan.
app = create_app(start_scheduler=True)
