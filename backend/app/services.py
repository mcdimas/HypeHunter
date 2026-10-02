import hashlib
import re
from datetime import timezone
from urllib.parse import urlparse

from fastapi import HTTPException, status
from sqlalchemy import func, or_
from sqlmodel import Session, select

from .models import AppEvent, Competitor, ImportJob, Reel, Remix, TranslationBatch, utc_now
from .schemas import CompetitorRead, ImportJobRead, ReelRead, RemixRead


HANDLE_PATTERN = re.compile(r"^[A-Za-z0-9._]{1,30}$")
def normalize_instagram_account(value: str) -> tuple[str, str]:
    candidate = value.strip().rstrip("/")
    if candidate.startswith("@"):
        handle = candidate[1:]
    elif "instagram.com" in candidate.lower():
        parsed = urlparse(candidate if "://" in candidate else f"https://{candidate}")
        if parsed.netloc.lower() not in {"instagram.com", "www.instagram.com"}:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Некорректный Instagram URL")
        handle = parsed.path.strip("/").split("/")[0]
    else:
        handle = candidate

    if not HANDLE_PATTERN.fullmatch(handle):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Введите Instagram URL или имя аккаунта",
        )

    normalized = f"@{handle.lower()}"
    return normalized, f"https://instagram.com/{handle.lower()}"


def normalize_account(value: str, platform: str) -> tuple[str, str]:
    if platform == "reels":
        return normalize_instagram_account(value)
    candidate = value.strip().rstrip("/")
    if "://" in candidate or "threads." in candidate:
        parsed = urlparse(candidate if "://" in candidate else f"https://{candidate}")
        if parsed.scheme not in {"https", "http"} or parsed.hostname not in {"threads.com", "www.threads.com", "threads.net", "www.threads.net"}:
            raise HTTPException(422, "Введите ссылку на профиль Threads")
        candidate = parsed.path.strip("/")
    handle = candidate.lstrip("@").lower()
    if not HANDLE_PATTERN.fullmatch(handle):
        raise HTTPException(422, "Введите имя аккаунта или ссылку на профиль Threads")
    return f"@{handle}", f"https://www.threads.com/@{handle}"


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "remix"


def unique_remix_slug(session: Session, title: str) -> str:
    base = slugify(title)
    slug = base
    suffix = 2
    while session.exec(select(Remix.id).where(Remix.slug == slug)).first() is not None:
        slug = f"{base}-{suffix}"
        suffix += 1
    return slug


def original_reel_fields(reel: Reel) -> tuple[str, str, str]:
    """Split the source Reel text into hook, full script and CTA."""
    script = (reel.transcript or reel.caption or reel.hook or reel.title).strip()
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", script)
        if sentence.strip()
    ]
    hook = (sentences[0] if sentences else script)[:4000]
    cta = (sentences[-1] if len(sentences) > 1 else "")[:4000]
    return hook, script, cta


def source_text_hash(reel: Reel) -> str:
    _, script, _ = original_reel_fields(reel)
    return hashlib.sha256(script.encode("utf-8")).hexdigest()


def reel_is_russian(reel: Reel) -> bool:
    _, script, _ = original_reel_fields(reel)
    cyrillic = len(re.findall(r"[А-Яа-яЁё]", script))
    latin = len(re.findall(r"[A-Za-z]", script))
    return cyrillic >= 20 and cyrillic >= latin


def mark_russian_source_ready(reel: Reel) -> bool:
    """Use a Russian source as the editable Russian version without an LLM call."""
    if not reel_is_russian(reel):
        return False
    hook, script, cta = original_reel_fields(reel)
    reel.translated_hook = hook
    reel.translated_script = script
    reel.translated_cta = cta
    reel.translation_status = "completed"
    reel.translation_error = None
    reel.translation_source_hash = source_text_hash(reel)
    reel.translation_model = "source-ru"
    reel.translation_reasoning_effort = "not_required"
    reel.translated_at = utc_now()
    return True


def source_remix_fields(reel: Reel) -> tuple[str, str, str]:
    """Never present an untranslated source as a Russian working copy."""
    if (reel.translation_status == "completed" and (reel.translated_script or "").strip()
            and reel.translation_source_hash == source_text_hash(reel)):
        return (
            (reel.translated_hook or "")[:4000],
            (reel.translated_script or "")[:12000],
            (reel.translated_cta or "")[:4000],
        )
    return original_reel_fields(reel) if reel_is_russian(reel) else ("", "", "")


def reel_read(reel: Reel) -> ReelRead:
    original_hook, original_script, original_cta = original_reel_fields(reel)
    return ReelRead(
        id=reel.id,
        platform=reel.platform,
        remix_count=len(reel.remixes),
        competitor_id=reel.competitor_id,
        external_id=reel.external_id,
        title=reel.title,
        hook=reel.hook,
        caption=reel.caption,
        transcript=reel.transcript,
        topics=reel.topics,
        author=reel.author,
        views=reel.views,
        likes_count=reel.likes_count,
        comments_count=reel.comments_count,
        shares_count=reel.shares_count,
        duration_seconds=reel.duration_seconds,
        published_at=reel.published_at,
        original_url=reel.original_url,
        thumbnail_url=reel.thumbnail_url,
        media_path=reel.media_path,
        thumb_variant=reel.thumb_variant,
        is_saved=reel.is_saved,
        content_status=reel.content_status,
        original_hook=original_hook,
        original_script=original_script,
        original_cta=original_cta,
        translated_hook=reel.translated_hook,
        translated_script=reel.translated_script,
        translated_cta=reel.translated_cta,
        translation_status=reel.translation_status,
        translation_error=reel.translation_error,
        translation_model=reel.translation_model,
        translation_reasoning_effort=reel.translation_reasoning_effort,
        translated_at=reel.translated_at,
        created_at=reel.created_at,
        updated_at=reel.updated_at,
    )


def record_event(session: Session, event_type: str, entity_type: str, entity_id: int | None, payload: dict | None = None) -> None:
    model = {"competitor": Competitor, "reel": Reel, "remix": Remix,
             "import_job": ImportJob, "translation_batch": TranslationBatch}.get(entity_type)
    entity = session.get(model, entity_id) if model and entity_id is not None else None
    if not entity:
        raise ValueError("Cannot record an event without an owned entity")
    session.add(
        AppEvent(
            user_id=entity.user_id,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload or {},
        )
    )


def competitor_read(session: Session, competitor: Competitor) -> CompetitorRead:
    reel_count = session.exec(
        select(func.count(Reel.id)).where(Reel.competitor_id == competitor.id, Reel.user_id == competitor.user_id)
    ).one()
    return CompetitorRead(
        id=competitor.id,
        platform=competitor.platform,
        handle=competitor.handle,
        profile_url=competitor.profile_url,
        category=competitor.category,
        language=competitor.language,
        avatar_url=competitor.avatar_url,
        is_active=competitor.is_active,
        reel_count=reel_count,
        last_import_at=competitor.last_import_at,
        created_at=competitor.created_at,
        updated_at=competitor.updated_at,
    )


def import_read(session: Session, job: ImportJob) -> ImportJobRead:
    competitor = session.get(Competitor, job.competitor_id)
    if competitor and competitor.user_id != job.user_id:
        competitor = None
    stage = job.stage
    stage_message = job.stage_message
    progress_current = job.progress_current
    result_summary = {}

    if job.status == "completed":
        progress_current = job.progress_total
        if job.imported_count < job.requested_count:
            missing_count = job.requested_count - job.imported_count
            stage = "partial"
            stage_message = (
                f"Apify вернул {job.imported_count} доступных материалов из {job.requested_count}. "
                f"Ещё {missing_count} не были получены от источника."
            )
            result_summary.setdefault("missing_count", missing_count)
            result_summary.setdefault(
                "shortfall_reason",
                "При сохранении потерь нет. Недостающие публикации могли быть закреплены, удалены, ограничены или недоступны для публичной выгрузки.",
            )
        else:
            stage = "completed"
            stage_message = f"Сохранено материалов: {job.imported_count} из {job.requested_count}"
    elif job.status == "failed":
        stage = "failed"
        stage_message = job.error_message or "Импорт завершился с ошибкой"
        progress_current = job.progress_total
    elif job.status == "cancelled":
        stage = "cancelled"
        stage_message = "Импорт остановлен пользователем"
    elif job.status == "waiting_for_token":
        stage = "waiting_for_token"
        stage_message = "Конкурент сохранён. Для запуска нужен Apify token"

    return ImportJobRead(
        id=job.id,
        competitor_id=job.competitor_id,
        competitor_handle=competitor.handle if competitor else "Удалённый аккаунт",
        platform=competitor.platform if competitor else "reels",
        provider=job.provider,
        status=job.status,
        requested_count=job.requested_count,
        imported_count=job.imported_count,
        error_message=job.error_message,
        stage=stage,
        stage_message=stage_message,
        progress_current=progress_current,
        progress_total=job.progress_total,
        result_summary=result_summary,
        started_at=job.started_at,
        completed_at=job.completed_at,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def remix_read(session: Session, remix: Remix) -> RemixRead:
    source = session.get(Reel, remix.source_reel_id) if remix.source_reel_id else None
    if source and source.user_id != remix.user_id:
        source = None
    return RemixRead(
        id=remix.id,
        slug=remix.slug,
        source_reel_id=remix.source_reel_id,
        title=remix.title,
        brief=remix.brief,
        hook=remix.hook,
        script=remix.script,
        cta=remix.cta,
        thread_text=remix.thread_text,
        status=remix.status,
        format=remix.format,
        production_stage=remix.production_stage,
        scheduled_at=remix.scheduled_at,
        published_at=remix.published_at,
        source_reel=reel_read(source) if source else None,
        created_at=remix.created_at,
        updated_at=remix.updated_at.replace(tzinfo=timezone.utc) if remix.updated_at.tzinfo is None else remix.updated_at,
    )


def reel_search_clause(query: str):
    pattern = f"%{query.strip()}%"
    return or_(Reel.search_text.ilike(pattern), Reel.translated_hook.ilike(pattern), Reel.translated_script.ilike(pattern))
