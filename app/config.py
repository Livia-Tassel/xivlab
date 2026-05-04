from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"
    app_base_url: str = "http://localhost:8001"
    secret_key: str = "changeme"
    database_url: str = "sqlite+aiosqlite:///./data/app.db"

    email_backend: str = "mock"  # 'mock' | 'resend'
    resend_api_key: str = ""
    resend_from_email: str = "noreply@xivlab.local"
    admin_emails: str = ""  # comma-separated

    embedding_provider: str = "mock"  # 'mock' | 'openai' | 'zhipu' | 'siliconflow'
    embedding_model: str = "text-embedding-3-small"
    openai_api_key: str = ""

    arxiv_categories: str = "cs.AI,cs.LG,cs.CL"

    @property
    def admin_email_list(self) -> list[str]:
        return [e.strip() for e in self.admin_emails.split(",") if e.strip()]

    @property
    def arxiv_category_list(self) -> list[str]:
        return [c.strip() for c in self.arxiv_categories.split(",") if c.strip()]


def get_settings() -> Settings:
    return Settings()


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
