from datetime import datetime, timezone

from sqlalchemy import BigInteger, Column, DateTime, JSON, String, Text, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    display_name: str = Field(default="", max_length=255)
    name_edited: bool = Field(default=False)
    avatar_path: str | None = Field(default=None, max_length=1024)
    avatar_edited: bool = Field(default=False)
    status: str = Field(default="active", max_length=32, index=True)
    created_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    last_login_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class AuthIdentity(SQLModel, table=True):
    __tablename__ = "auth_identities"
    __table_args__ = (UniqueConstraint("provider", "provider_subject", name="uq_auth_identity_provider_subject"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    provider: str = Field(max_length=32)
    provider_subject: str = Field(max_length=255)
    verified_attributes: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))


class LoginSession(SQLModel, table=True):
    __tablename__ = "auth_sessions"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    token_hash: str = Field(sa_column=Column(String(64), nullable=False, index=True, unique=True))
    created_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    last_seen_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    revoked_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    user_agent: str = Field(default="", max_length=255)
    ip_hash: str = Field(default="", max_length=64)


class AuthChallenge(SQLModel, table=True):
    __tablename__ = "auth_challenges"

    id: str = Field(sa_column=Column(String(64), primary_key=True))
    purpose: str = Field(default="login", max_length=16)
    browser_secret_hash: str = Field(max_length=64)
    code_mac: str = Field(max_length=64)
    state: str = Field(default="pending", max_length=32, index=True)
    telegram_user_id: int | None = Field(default=None, sa_column=Column(BigInteger))
    telegram_profile: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    attempts: int = Field(default=0)
    return_path: str = Field(default="/", max_length=512)
    ip_hash: str = Field(default="", max_length=64)
    created_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    approved_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    consumed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class EmailChallenge(SQLModel, table=True):
    __tablename__ = "email_challenges"

    id: str = Field(sa_column=Column(String(64), primary_key=True))
    email: str = Field(max_length=254)
    browser_secret_hash: str = Field(max_length=64)
    code_mac: str = Field(max_length=64)
    state: str = Field(default="sending", max_length=16)
    attempts: int = Field(default=0)
    return_path: str = Field(default="/today", max_length=512)
    created_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False, index=True))
    consumed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class OAuthRequest(SQLModel, table=True):
    __tablename__ = "oauth_requests"

    id: str = Field(sa_column=Column(String(64), primary_key=True))
    browser_secret_hash: str = Field(max_length=64)
    purpose: str = Field(default="login", max_length=16)
    link_session_id: int | None = Field(default=None, foreign_key="auth_sessions.id")
    return_path: str = Field(default="/today", max_length=512)
    state: str = Field(default="pending", max_length=16)
    created_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False, index=True))
    consumed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class TelegramUpdate(SQLModel, table=True):
    __tablename__ = "telegram_updates"

    update_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    created_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))


class AuthRateLimit(SQLModel, table=True):
    __tablename__ = "auth_rate_limits"

    key_hash: str = Field(sa_column=Column(String(64), primary_key=True))
    count: int = Field(default=0)
    window_started_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))


class Competitor(SQLModel, table=True):
    __tablename__ = "competitors"
    __table_args__ = (
        UniqueConstraint("user_id", "platform", "handle", name="uq_competitor_user_platform_handle"),
        UniqueConstraint("user_id", "profile_url", name="uq_competitor_user_profile_url"),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    handle: str = Field(sa_column=Column(String(128), index=True, nullable=False))
    platform: str = Field(default="reels", max_length=16, index=True)
    profile_url: str = Field(sa_column=Column(String(512), nullable=False))
    category: str = Field(default="Без категории", max_length=128)
    language: str = Field(default="EN", max_length=16)
    avatar_url: str | None = Field(default=None, max_length=1024)
    is_active: bool = Field(default=True, index=True)
    last_import_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    created_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))

    reels: list["Reel"] = Relationship(back_populates="competitor")
    import_jobs: list["ImportJob"] = Relationship(back_populates="competitor")


class Reel(SQLModel, table=True):
    __tablename__ = "reels"
    __table_args__ = (UniqueConstraint("user_id", "external_id", name="uq_reel_user_external_id"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    competitor_id: int = Field(foreign_key="competitors.id", index=True)
    platform: str = Field(default="reels", max_length=16, index=True)
    external_id: str = Field(sa_column=Column(String(255), index=True, nullable=False))
    title: str = Field(max_length=255, index=True)
    hook: str = Field(sa_column=Column(Text, nullable=False))
    caption: str = Field(default="", sa_column=Column(Text, nullable=False))
    transcript: str | None = Field(default=None, sa_column=Column(Text))
    topics: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    search_text: str = Field(default="", sa_column=Column(Text, nullable=False))
    author: str = Field(max_length=128, index=True)
    views: int | None = Field(default=None, ge=0)
    likes_count: int | None = Field(default=None, ge=0)
    comments_count: int | None = Field(default=None, ge=0)
    shares_count: int | None = Field(default=None, ge=0)
    duration_seconds: int | None = Field(default=None, ge=0)
    published_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    original_url: str | None = Field(default=None, max_length=1024)
    thumbnail_url: str | None = Field(default=None, max_length=1024)
    media_path: str | None = Field(default=None, max_length=1024)
    thumb_variant: int = Field(default=1, ge=1, le=4)
    is_saved: bool = Field(default=False, index=True)
    content_status: str = Field(default="not_started", max_length=32, index=True)
    translated_hook: str | None = Field(default=None, sa_column=Column(Text))
    translated_script: str | None = Field(default=None, sa_column=Column(Text))
    translated_cta: str | None = Field(default=None, sa_column=Column(Text))
    translation_status: str = Field(default="pending", max_length=32, index=True)
    translation_error: str | None = Field(default=None, sa_column=Column(Text))
    translation_source_hash: str | None = Field(default=None, max_length=64, index=True)
    translation_model: str | None = Field(default=None, max_length=128)
    translation_reasoning_effort: str | None = Field(default=None, max_length=32)
    translated_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    created_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))

    competitor: Competitor | None = Relationship(back_populates="reels")
    remixes: list["Remix"] = Relationship(back_populates="source_reel")


class Remix(SQLModel, table=True):
    __tablename__ = "remixes"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    slug: str = Field(sa_column=Column(String(255), unique=True, index=True, nullable=False))
    source_reel_id: int | None = Field(default=None, foreign_key="reels.id", index=True)
    title: str = Field(max_length=255)
    brief: str = Field(default="", sa_column=Column(Text, nullable=False))
    hook: str = Field(default="", sa_column=Column(Text, nullable=False))
    script: str = Field(default="", sa_column=Column(Text, nullable=False))
    cta: str = Field(default="", sa_column=Column(Text, nullable=False))
    thread_text: str = Field(default="", sa_column=Column(Text, nullable=False))
    status: str = Field(default="idea", max_length=32, index=True)
    format: str = Field(default="reels", max_length=16, index=True)
    production_stage: str = Field(default="script", max_length=16)
    scheduled_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    published_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    created_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))

    source_reel: Reel | None = Relationship(back_populates="remixes")


class ImportJob(SQLModel, table=True):
    __tablename__ = "import_jobs"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    competitor_id: int = Field(foreign_key="competitors.id", index=True)
    provider: str = Field(default="apify", max_length=32)
    status: str = Field(default="waiting_for_token", max_length=32, index=True)
    requested_count: int = Field(default=20, ge=1, le=100)
    imported_count: int = Field(default=0, ge=0)
    error_message: str | None = Field(default=None, sa_column=Column(Text))
    actor_run_id: str | None = Field(default=None, max_length=128)
    dataset_id: str | None = Field(default=None, max_length=128)
    stage: str = Field(default="queued", max_length=64, index=True)
    stage_message: str = Field(default="Задача поставлена в очередь", sa_column=Column(Text, nullable=False))
    progress_current: int = Field(default=2, ge=0)
    progress_total: int = Field(default=8, ge=1)
    debug_log: list[dict] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    result_summary: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    started_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    completed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    created_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))

    competitor: Competitor | None = Relationship(back_populates="import_jobs")


class AppEvent(SQLModel, table=True):
    __tablename__ = "app_events"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    event_type: str = Field(max_length=128, index=True)
    entity_type: str = Field(max_length=64, index=True)
    entity_id: int | None = Field(default=None, index=True)
    payload: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))


class TranslationBatch(SQLModel, table=True):
    __tablename__ = "translation_batches"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    status: str = Field(default="queued", max_length=32, index=True)
    reel_ids: list[int] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    item_count: int = Field(default=0, ge=0)
    translated_count: int = Field(default=0, ge=0)
    model: str = Field(default="gpt-5.6-sol", max_length=128)
    reasoning_effort: str = Field(default="medium", max_length=32)
    prompt: str = Field(default="", sa_column=Column(Text, nullable=False))
    raw_response: str | None = Field(default=None, sa_column=Column(Text))
    stderr: str | None = Field(default=None, sa_column=Column(Text))
    exit_code: int | None = None
    error_message: str | None = Field(default=None, sa_column=Column(Text))
    started_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    completed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    created_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
