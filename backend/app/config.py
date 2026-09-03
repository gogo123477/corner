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
    # Web Push (VAPID). Generate once: `python -m app.jobs.push keygen`
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = "mailto:hello@example.com"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"  # comma-separated


@lru_cache
def get_settings() -> Settings:
    return Settings()
