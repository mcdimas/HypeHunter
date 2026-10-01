from datetime import datetime
from typing import Literal
from pydantic import model_validator

from sqlmodel import Field, SQLModel


class CompetitorCreate(SQLModel):
    account: str = Field(min_length=2, max_length=512)
    platform: Literal["reels", "threads"] = "reels"
    requested_count: int = Field(default=20, ge=1, le=20)
    category: str = Field(default="Без категории", max_length=128)
    language: str = Field(default="EN", max_length=16)


class CompetitorUpdate(SQLModel):
    category: str | None = Field(default=None, max_length=128)
    language: str | None = Field(default=None, max_length=16)
    is_active: bool | None = None


class CompetitorRead(SQLModel):
    id: int
    platform: str
    handle: str
    profile_url: str
    category: str
    language: str
    avatar_url: str | None
    is_active: bool
    reel_count: int
    last_import_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ReelRead(SQLModel):
    id: int
    platform: str
    remix_count: int = 0
    competitor_id: int
    external_id: str
    title: str
    hook: str
    caption: str
    transcript: str | None
    topics: list[str]
    author: str
    views: int | None
    likes_count: int | None
    comments_count: int | None
    shares_count: int | None
    duration_seconds: int | None
    published_at: datetime | None
    original_url: str | None
    thumbnail_url: str | None
    media_path: str | None
    thumb_variant: int
    is_saved: bool
    content_status: str
    original_hook: str
    original_script: str
    original_cta: str
    translated_hook: str | None
    translated_script: str | None
    translated_cta: str | None
    translation_status: str
    translation_error: str | None
    translation_model: str | None
    translation_reasoning_effort: str | None
    translated_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ReelUpdate(SQLModel):
    is_saved: bool | None = None
    content_status: Literal["not_started", "ready", "published"] | None = None


class ReelPage(SQLModel):
    items: list[ReelRead]
    page: int
    page_size: int
    total: int
    page_count: int


class RemixCreate(SQLModel):
    source_reel_id: int | None = None
    format: Literal["reels", "threads"] | None = None
    title: str | None = Field(default=None, max_length=255)
    brief: str = Field(default="", max_length=4000)


class RemixDerive(SQLModel):
    format: Literal["reels", "threads"]


class RemixUpdate(SQLModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    brief: str | None = Field(default=None, max_length=4000)
    hook: str | None = Field(default=None, max_length=4000)
    script: str | None = Field(default=None, max_length=12000)
    cta: str | None = Field(default=None, max_length=4000)
    thread_text: str | None = Field(default=None, max_length=500)
    status: Literal["idea", "in_progress", "ready", "published"] | None = None
    format: Literal["reels", "threads"] | None = None
    production_stage: Literal["script", "filming", "editing", "text"] | None = None
    scheduled_at: datetime | None = None
    published_at: datetime | None = None
    expected_updated_at: datetime | None = None

    @model_validator(mode="after")
    def validate_values(self):
        for name in self.model_fields_set:
            value = getattr(self, name)
            if value is None and name not in {"scheduled_at", "published_at", "expected_updated_at"}:
                raise ValueError(f"Поле {name} не может быть пустым")
            if name in {"scheduled_at", "published_at", "expected_updated_at"} and value is not None and value.tzinfo is None:
                raise ValueError("Дата должна содержать временную зону")
        return self


class RemixRead(SQLModel):
    id: int
    slug: str
    source_reel_id: int | None
    title: str
    brief: str
    hook: str
    script: str
    cta: str
    thread_text: str
    status: str
    format: str
    production_stage: str
    scheduled_at: datetime | None
    published_at: datetime | None
    source_reel: ReelRead | None = None
    created_at: datetime
    updated_at: datetime


class ImportCreate(SQLModel):
    competitor_id: int
    requested_count: int = Field(default=20, ge=1, le=100)


class ImportJobRead(SQLModel):
    id: int
    competitor_id: int
    competitor_handle: str
    platform: str = "reels"
    provider: str
    status: str
    requested_count: int
    imported_count: int
    error_message: str | None
    stage: str
    stage_message: str
    progress_current: int
    progress_total: int
    result_summary: dict
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TranslationBatchRead(SQLModel):
    id: int
    status: str
    reel_ids: list[int]
    item_count: int
    translated_count: int
    model: str
    reasoning_effort: str
    exit_code: int | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TranslationSummaryRead(SQLModel):
    total: int
    translated: int
    pending: int
    running: int
    failed: int
    eligible: int
    active: bool
    cli_available: bool
    cli_authenticated: bool
    model: str
    reasoning_effort: str
    batch_size: int


class TranslationOverviewRead(SQLModel):
    summary: TranslationSummaryRead
    batches: list[TranslationBatchRead]


class ReadinessRead(SQLModel):
    database: str
    apify_configured: bool
    media_root: str
    ready_for_apify: bool
    codex_cli_available: bool
    codex_cli_authenticated: bool
    codex_model: str
    codex_reasoning_effort: str
    project_timezone: str = "Europe/Moscow"
    threads_import_configured: bool = False


class HealthRead(SQLModel):
    status: str
    database: str
