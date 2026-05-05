from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import PROJECT_ROOT, get_settings
from app.routers import auth as auth_router
from app.routers import me as me_router
from app.routers import pages as pages_router
from app.routers import rss as rss_router
from app.routers import tasks as tasks_router


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="xivLab",
        description="Research AI tools — arXiv digest + PromptHub",
        version="0.1.0",
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "env": settings.app_env}

    app.mount(
        "/static",
        StaticFiles(directory=str(PROJECT_ROOT / "static")),
        name="static",
    )
    app.include_router(auth_router.router)
    app.include_router(me_router.router)
    app.include_router(tasks_router.router)
    app.include_router(rss_router.router)
    app.include_router(pages_router.router)
    return app


app = create_app()
