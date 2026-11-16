import re
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "local.env"), extra="ignore")

    debug: bool = False

    # Telegram
    telegram_bot_token: str
    project_url: str = ""
    # telegram ids that are created as bot admins on startup: `1,2` or `[1, 2]`
    telegram_admin_ids: str = ""

    # Telegram webhook secret_token (the GitLab signing token lives in the DB, see admin).
    # Only A-Z a-z 0-9 _ - (Telegram limitation). Empty = no check.
    webhook_secret: str = ""

    # Database: either DATABASE_URL or DB_* parts
    database_url: str = ""
    db_name: str = ""
    db_user: str = ""
    db_password: str = ""
    db_host: str = "localhost"
    db_port: int = 5432

    redis_url: str = "redis://127.0.0.1:6379/0"

    # sqladmin panel (disabled while the password is empty)
    secret_key: str = "change-me"
    admin_username: str = "admin"
    admin_password: str = ""

    @model_validator(mode="after")
    def _normalize(self) -> "Settings":
        self.project_url = self.project_url.rstrip("/")
        return self

    @property
    def sqlalchemy_url(self) -> str | URL:
        if self.database_url:
            url = self.database_url
            if url.startswith("postgresql://"):
                url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
            return url
        return URL.create(
            "postgresql+asyncpg",
            username=self.db_user or None,
            password=self.db_password or None,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name or None,
        )

    @property
    def admin_ids(self) -> list[int]:
        """Accepts `1,2`, `[1, 2]` and `["1", "2"]`."""
        try:
            return [int(x) for x in re.findall(r"-?\d+", self.telegram_admin_ids)]
        except ValueError:
            return []


@lru_cache
def get_settings() -> Settings:
    return Settings()
