from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    app_name: str = "Hype Hunter API"
    database_url: str = "postgresql+psycopg://ai_producer:ai-producer-local@postgres:5432/ai_producer"
    media_root: Path = Path("/data/media")
    apify_token: str | None = None
    apify_actor_id: str = "apify/instagram-reel-scraper"
    apify_profile_actor_id: str = "apify/instagram-profile-scraper"
    apify_threads_actor_id: str = "webdata_labs/threads-scraper"
    apify_threads_max_charge_usd: float = 0.10
    project_timezone: str = "Europe/Moscow"
    apify_import_limit: int = 20
    apify_max_charge_usd: float = 1.10
    apify_profile_max_charge_usd: float = 0.05
    openai_api_key: str = Field(default="", repr=False)
    openai_enabled: bool = False
    openai_model: str = "gpt-5.6-luna"
    openai_reasoning_effort: Literal["none", "low", "medium", "high", "xhigh", "max"] = "high"
    openai_timeout_seconds: int = Field(default=180, ge=10, le=600)
    openai_max_input_chars: int = Field(default=60000, ge=1000, le=120000)
    openai_max_output_tokens: int = Field(default=16000, ge=1000, le=32000)
    translation_batch_size: int = Field(default=5, ge=1, le=10)
    translation_auto_start: bool = True
    translation_user_daily_batches: int = Field(default=50, ge=1, le=1000)
    translation_global_daily_batches: int = Field(default=200, ge=1, le=10000)
    cors_origins: str = "http://127.0.0.1:4173,http://localhost:4173"
    public_origin: str = ""
    telegram_bot_token: str = ""
    telegram_bot_username: str = ""
    telegram_webhook_secret: str = ""
    telegram_delivery_mode: Literal["webhook", "polling"] = "webhook"
    owner_telegram_id: int | None = None
    auth_code_secret: str = ""
    auth_challenge_minutes: int = 5
    auth_session_days: int = 30
    auth_idle_days: int = 7
    yandex_client_id: str = ""
    unisender_go_api_key: str = ""
    email_from_address: str = ""
    email_from_name: str = "Hype Hunter"
    email_code_minutes: int = Field(default=5, ge=1, le=10)
    email_code_attempts: int = Field(default=5, ge=1, le=5)
    email_resend_seconds: int = Field(default=60, ge=60)
    email_hourly_limit: int = Field(default=100, ge=1)

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
