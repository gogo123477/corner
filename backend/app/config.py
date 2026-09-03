from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CORNER_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./corner.db"
    auth_mode: Literal["dev", "jwt"] = "dev"
    jwt_secret: str = ""
    jwt_audience: str = "authenticated"  # Supabase default
    brief_model: str = "claude-opus-5"
    brief_language: str = "en"


@lru_cache
def get_settings() -> Settings:
    return Settings()
