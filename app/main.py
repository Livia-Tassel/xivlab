from fastapi import FastAPI

from app.config import get_settings


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

    return app


app = create_app()
