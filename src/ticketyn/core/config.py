from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str

    @field_validator("database_url")
    @classmethod
    def require_postgresql(cls, value: str) -> str:
        if make_url(value).drivername != "postgresql+psycopg":
            raise ValueError("DATABASE_URL debe usar postgresql+psycopg")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
