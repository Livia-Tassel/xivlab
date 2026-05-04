from fastapi import FastAPI

from app.config import get_settings
from app.routers import auth as auth_router
from app.routers import me as me_router


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

    app.include_router(auth_router.router)
    app.include_router(me_router.router)
    return app


app = create_app()
