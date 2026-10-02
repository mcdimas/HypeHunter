import math
from datetime import datetime, timedelta, timezone
from typing import Literal
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from apify_client import ApifyClient
from sqlalchemy import and_, delete, func, or_, text, update
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select
from pydantic import BaseModel, ConfigDict

from .apify_import import ACTIVE_IMPORT_STATUSES, run_apify_import
from .auth import require_user_id
from .translation import (
    ACTIVE_TRANSLATION_STATUSES,
    run_translation_backfill,
    translation_counts,
)
from .openai_client import translation_ready, translation_model, translation_effort
from .trial import reserve_trial, trial_user
from .config import Settings, get_settings
from .database import get_session
from .models import AppEvent, AuthIdentity, Competitor, ImportJob, Reel, Remix, TranslationBatch, User
from .schemas import (
    CompetitorCreate,
    CompetitorRead,
    CompetitorUpdate,
    HealthRead,
    ImportCreate,
    ImportJobRead,
    ReadinessRead,
    ReelPage,
    ReelRead,
    ReelUpdate,
    RemixCreate,
    RemixDerive,
    RemixRead,
    RemixUpdate,
    TranslationBatchRead,
    TranslationOverviewRead,
    TranslationSummaryRead,
)
from .services import (
    competitor_read,
    import_read,
    normalize_account,
    record_event,
    reel_read,
    reel_search_clause,
    remix_read,
    source_remix_fields,
    unique_remix_slug,
    utc_now,
)


router = APIRouter(prefix="/api")


class WorkspaceClear(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmation: Literal["УДАЛИТЬ"]


@router.delete("/workspace")
def clear_workspace(payload: WorkspaceClear, session: Session = Depends(get_session),
                    user_id: int = Depends(require_user_id), settings: Settings = Depends(get_settings)) -> dict:
    # Same user lock as imports: do not race a new reservation or active worker.
    trial_user(session, user_id)
    for model, statuses in ((ImportJob, ACTIVE_IMPORT_STATUSES), (TranslationBatch, ACTIVE_TRANSLATION_STATUSES)):
        if session.exec(select(model.id).where(model.user_id == user_id, model.status.in_(statuses)).limit(1)).first():
            raise HTTPException(409, "Сначала дождитесь завершения загрузки и перевода или остановите загрузку.")
    media_paths = {row.media_path for row in session.exec(select(Reel).where(Reel.user_id == user_id)).all()}
    media_paths.update(row.avatar_url for row in session.exec(select(Competitor).where(Competitor.user_id == user_id)).all())
    counts = {}
    for model in (Remix, TranslationBatch, AppEvent, ImportJob, Reel, Competitor):
        counts[model.__tablename__] = session.exec(select(func.count(model.id)).where(model.user_id == user_id)).one()
        session.exec(delete(model).where(model.user_id == user_id))
    # Do not remove a media file still referenced by another account/profile.
    removable = []
    for path in media_paths:
        if not path:
            continue
        referenced = any(session.exec(select(model.id).where(field == path).limit(1)).first() is not None
                         for model, field in ((Reel, Reel.media_path), (Competitor, Competitor.avatar_url), (User, User.avatar_path)))
        if not referenced:
            removable.append(path)
    # Account, identities, sessions, preferences and lifetime trial usage remain intact.
    session.commit()
    _remove_media_files(settings.media_root, removable)
    return {"deleted": counts}


@router.get("/health", response_model=HealthRead)
def health(session: Session = Depends(get_session)) -> HealthRead:
    session.exec(select(1)).one()
    return HealthRead(status="ok", database="connected")


@router.get("/readiness", response_model=ReadinessRead)
def readiness(
    user_id: int = Depends(require_user_id),
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
) -> ReadinessRead:
    if not settings.owner_telegram_id:
        raise HTTPException(404, "Страница не найдена")
    # Detailed server diagnostics are not part of a normal user account.
    owner = session.exec(select(AuthIdentity.user_id).where(
        AuthIdentity.provider == "telegram",
        AuthIdentity.provider_subject == str(settings.owner_telegram_id),
    )).first()
    if owner != user_id:
        raise HTTPException(404, "Страница не найдена")
    return ReadinessRead(
        database="postgresql",
        apify_configured=bool(settings.apify_token),
        media_root=str(settings.media_root),
        ready_for_apify=True,
        ai_configured=translation_ready(settings),
        ai_model=settings.openai_model,
        project_timezone=settings.project_timezone,
        threads_import_configured=bool(settings.apify_token and settings.apify_threads_actor_id),
    )


def _check_import_budget(session: Session, user_id: int, settings: Settings) -> None:
    if not settings.apify_token:
        return
    # Serialize budget checks across API instances before creating a paid job.
    if session.bind.dialect.name == "postgresql":
        session.exec(text("SELECT pg_advisory_xact_lock(34962401)")).one()
    since = utc_now() - timedelta(days=1)
    total = session.exec(select(func.count(ImportJob.id)).where(
        ImportJob.created_at >= since, ImportJob.status != "waiting_for_token",
    )).one()
    if total >= 50:
        raise HTTPException(429, "Дневной лимит загрузок исчерпан")
    owner_id = None
    if settings.owner_telegram_id:
        owner_id = session.exec(select(AuthIdentity.user_id).where(
            AuthIdentity.provider == "telegram",
            AuthIdentity.provider_subject == str(settings.owner_telegram_id),
        )).first()
    personal = session.exec(select(func.count(ImportJob.id)).where(
        ImportJob.user_id == user_id, ImportJob.created_at >= since,
        ImportJob.status != "waiting_for_token",
    )).one()
    if personal >= (30 if owner_id == user_id else 4):
        raise HTTPException(429, "Ваш дневной лимит загрузок исчерпан")
    active = session.exec(select(func.count(ImportJob.id)).where(
        ImportJob.status.in_(ACTIVE_IMPORT_STATUSES),
    )).one()
    if active >= 3:
        raise HTTPException(429, "Сейчас выполняется слишком много загрузок. Попробуйте позже")


@router.get("/competitors", response_model=list[CompetitorRead])
def list_competitors(user_id: int = Depends(require_user_id), session: Session = Depends(get_session)) -> list[CompetitorRead]:
    competitors = session.exec(select(Competitor).where(Competitor.user_id == user_id).order_by(Competitor.created_at)).all()
    return [competitor_read(session, competitor) for competitor in competitors]


@router.get("/trial")
def trial_status(user_id: int = Depends(require_user_id), session: Session = Depends(get_session)):
    user = session.get(User, user_id)
    return {"limit": user.trial_reels_limit, "used": user.trial_reels_used,
            "remaining": None if user.trial_reels_limit is None else max(0, user.trial_reels_limit - user.trial_reels_used)}


@router.post("/competitors", response_model=CompetitorRead, status_code=status.HTTP_201_CREATED)
def create_competitor(
    payload: CompetitorCreate,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    user_id: int = Depends(require_user_id),
) -> CompetitorRead:
    handle, profile_url = normalize_account(payload.account, payload.platform)
    if handle == "@pantela.evgeny":
        raise HTTPException(422, "Этот аккаунт не добавляется без отдельного запроса владельца")
    _check_import_budget(session, user_id, settings)
    trial_limit = reserve_trial(session, user_id, payload.platform)
    competitor = Competitor(
        user_id=user_id,
        handle=handle,
        platform=payload.platform,
        profile_url=profile_url,
        category=payload.category,
        language=payload.language,
    )
    session.add(competitor)
    try:
        session.flush()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Этот конкурент уже добавлен") from error

    created_at = utc_now()
    initial_status = "queued" if settings.apify_token else "waiting_for_token"
    job = ImportJob(
        user_id=user_id,
        competitor_id=competitor.id,
        status=initial_status,
        requested_count=trial_limit if trial_limit is not None else min(payload.requested_count, settings.apify_import_limit, 20),
        trial_reels_limit=trial_limit,
        stage="queued" if settings.apify_token else "waiting_for_token",
        stage_message="Задача поставлена в очередь" if settings.apify_token else "Конкурент сохранён. Для запуска нужен Apify token",
        progress_current=2,
        progress_total=8,
        debug_log=[
            {
                "at": created_at.isoformat(),
                "stage": "database",
                "message": "Конкурент добавлен в PostgreSQL",
                "details": {"handle": competitor.handle},
            },
            {
                "at": created_at.isoformat(),
                "stage": "queued" if settings.apify_token else "waiting_for_token",
                "message": "Задача поставлена в очередь" if settings.apify_token else "Ожидаем Apify token",
            },
        ],
    )
    session.add(job)
    session.flush()
    record_event(
        session,
        "competitor.created",
        "competitor",
        competitor.id,
        {"handle": competitor.handle, "import_status": job.status},
    )
    session.commit()
    session.refresh(competitor)
    if settings.apify_token:
        background_tasks.add_task(run_apify_import, job.id)
    return competitor_read(session, competitor)


@router.patch("/competitors/{competitor_id}", response_model=CompetitorRead)
def update_competitor(
    competitor_id: int,
    payload: CompetitorUpdate,
    session: Session = Depends(get_session),
    user_id: int = Depends(require_user_id),
) -> CompetitorRead:
    competitor = session.get(Competitor, competitor_id)
    if not competitor or competitor.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Конкурент не найден")
    for key, value in payload.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(competitor, key, value)
    competitor.updated_at = utc_now()
    session.add(competitor)
    record_event(session, "competitor.updated", "competitor", competitor.id, payload.model_dump(exclude_unset=True))
    session.commit()
    session.refresh(competitor)
    return competitor_read(session, competitor)


def _media_file(media_root: Path, public_path: str | None) -> Path | None:
    if not public_path or not public_path.startswith("/media/"):
        return None
    root = media_root.resolve()
    candidate = (root / public_path.removeprefix("/media/")).resolve()
    return candidate if candidate.is_relative_to(root) else None


def _remove_media_files(media_root: Path, public_paths: list[str | None]) -> None:
    for public_path in set(public_paths):
        candidate = _media_file(media_root, public_path)
        if candidate and candidate.is_file():
            candidate.unlink()


def _remove_reels_from_translation_batches(session: Session, reel_ids: set[int], user_id: int) -> None:
    if not reel_ids:
        return
    for batch in session.exec(select(TranslationBatch).where(TranslationBatch.user_id == user_id)).all():
        remaining = [reel_id for reel_id in (batch.reel_ids or []) if reel_id not in reel_ids]
        if len(remaining) == len(batch.reel_ids or []):
            continue
        if not remaining:
            session.delete(batch)
            continue
        batch.reel_ids = remaining
        batch.item_count = len(remaining)
        batch.translated_count = min(batch.translated_count, batch.item_count)
        batch.updated_at = utc_now()
        session.add(batch)


@router.delete("/competitors/{competitor_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_competitor(
    competitor_id: int,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    user_id: int = Depends(require_user_id),
) -> None:
    trial_user(session, user_id)
    competitor = session.get(Competitor, competitor_id)
    if not competitor or competitor.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Конкурент не найден")

    reels = session.exec(select(Reel).where(Reel.competitor_id == competitor_id, Reel.user_id == user_id)).all()
    jobs = session.exec(select(ImportJob).where(ImportJob.competitor_id == competitor_id, ImportJob.user_id == user_id)).all()
    if any(job.status in ACTIVE_IMPORT_STATUSES for job in jobs):
        raise HTTPException(409, "Сначала остановите текущую загрузку этого конкурента.")
    reel_ids = {reel.id for reel in reels if reel.id is not None}
    job_ids = {job.id for job in jobs if job.id is not None}
    actor_run_ids = [job.actor_run_id for job in jobs if job.status in ACTIVE_IMPORT_STATUSES and job.actor_run_id]
    media_paths = [competitor.avatar_url, *(reel.media_path for reel in reels)]

    if reel_ids:
        session.exec(update(Remix).where(Remix.source_reel_id.in_(reel_ids), Remix.user_id == user_id).values(source_reel_id=None))
        session.exec(delete(AppEvent).where(and_(AppEvent.user_id == user_id, AppEvent.entity_type == "reel", AppEvent.entity_id.in_(reel_ids))))
    if job_ids:
        session.exec(delete(AppEvent).where(and_(AppEvent.user_id == user_id, AppEvent.entity_type == "import_job", AppEvent.entity_id.in_(job_ids))))
    session.exec(
        delete(AppEvent).where(
            AppEvent.user_id == user_id,
            or_(
                and_(AppEvent.entity_type == "competitor", AppEvent.entity_id == competitor_id),
                and_(AppEvent.entity_type == "reel", AppEvent.entity_id.in_(reel_ids or {-1})),
                and_(AppEvent.entity_type == "import_job", AppEvent.entity_id.in_(job_ids or {-1})),
            )
        )
    )
    _remove_reels_from_translation_batches(session, reel_ids, user_id)
    session.exec(delete(ImportJob).where(ImportJob.competitor_id == competitor_id, ImportJob.user_id == user_id))
    session.exec(delete(Reel).where(Reel.competitor_id == competitor_id, Reel.user_id == user_id))
    session.delete(competitor)
    session.commit()

    token = (settings.apify_token or "").strip()
    if token:
        for actor_run_id in actor_run_ids:
            try:
                ApifyClient(token).run(actor_run_id).abort(gracefully=False)
            except Exception:
                pass
    _remove_media_files(settings.media_root, media_paths)


@router.get("/reels", response_model=ReelPage)
def list_reels(
    q: str = Query(default="", max_length=255),
    competitor_id: int | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=4, ge=1, le=100),
    platform: Literal["reels", "threads"] | None = None,
    period: Literal["all", "7", "30", "90"] = "all",
    sort: Literal["newest", "oldest", "views", "likes", "comments", "shares"] = "newest",
    session: Session = Depends(get_session),
    user_id: int = Depends(require_user_id),
) -> ReelPage:
    filters = [Reel.user_id == user_id]
    if platform:
        filters.append(Reel.platform == platform)
    if period != "all":
        filters.append(Reel.published_at >= utc_now() - timedelta(days=int(period)))
    if competitor_id is not None:
        filters.append(Reel.competitor_id == competitor_id)
    for term in q.split():
        filters.append(reel_search_clause(term))

    statement = select(Reel).options(selectinload(Reel.remixes))
    count_statement = select(func.count(Reel.id))
    for filter_clause in filters:
        statement = statement.where(filter_clause)
        count_statement = count_statement.where(filter_clause)

    total = session.exec(count_statement).one()
    page_count = max(1, math.ceil(total / page_size))
    page = min(page, page_count)
    ordering = {
        "newest": Reel.published_at.desc().nulls_last(),
        "oldest": Reel.published_at.asc().nulls_last(),
        "views": Reel.views.desc().nulls_last(),
        "likes": Reel.likes_count.desc().nulls_last(),
        "comments": Reel.comments_count.desc().nulls_last(),
        "shares": Reel.shares_count.desc().nulls_last(),
    }[sort]
    items = session.exec(
        statement.order_by(ordering, Reel.id.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return ReelPage(
        items=[reel_read(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
        page_count=page_count,
    )


@router.get("/reels/{reel_id}", response_model=ReelRead)
def get_reel(reel_id: int, session: Session = Depends(get_session), user_id: int = Depends(require_user_id)) -> ReelRead:
    reel = session.get(Reel, reel_id)
    if not reel or reel.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reel не найден")
    return reel_read(reel)


@router.patch("/reels/{reel_id}", response_model=ReelRead)
def update_reel(reel_id: int, payload: ReelUpdate, session: Session = Depends(get_session), user_id: int = Depends(require_user_id)) -> ReelRead:
    reel = session.get(Reel, reel_id)
    if not reel or reel.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reel не найден")
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    for key, value in changes.items():
        setattr(reel, key, value)
    reel.updated_at = utc_now()
    session.add(reel)
    if "is_saved" in changes:
        record_event(session, "reel.saved" if reel.is_saved else "reel.unsaved", "reel", reel.id)
    if "content_status" in changes:
        record_event(session, "reel.content_status", "reel", reel.id, {"status": reel.content_status})
    session.commit()
    session.refresh(reel)
    return reel_read(reel)


@router.delete("/reels/{reel_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_reel(
    reel_id: int,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    user_id: int = Depends(require_user_id),
) -> None:
    reel = session.get(Reel, reel_id)
    if not reel or reel.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reel не найден")
    media_path = reel.media_path
    session.exec(update(Remix).where(Remix.source_reel_id == reel_id, Remix.user_id == user_id).values(source_reel_id=None))
    session.exec(delete(AppEvent).where(and_(AppEvent.user_id == user_id, AppEvent.entity_type == "reel", AppEvent.entity_id == reel_id)))
    _remove_reels_from_translation_batches(session, {reel_id}, user_id)
    session.delete(reel)
    session.commit()
    _remove_media_files(settings.media_root, [media_path])


@router.get("/remixes", response_model=list[RemixRead])
def list_remixes(session: Session = Depends(get_session), user_id: int = Depends(require_user_id)) -> list[RemixRead]:
    remixes = session.exec(select(Remix).where(Remix.user_id == user_id).order_by(Remix.updated_at.desc())).all()
    return [remix_read(session, remix) for remix in remixes]


@router.post("/remixes", response_model=RemixRead, status_code=status.HTTP_201_CREATED)
def create_remix(payload: RemixCreate, session: Session = Depends(get_session), user_id: int = Depends(require_user_id)) -> RemixRead:
    source = session.get(Reel, payload.source_reel_id) if payload.source_reel_id else None
    if payload.source_reel_id and (not source or source.user_id != user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Исходный Reel не найден")

    title = payload.title or (source.title if source else "Новый ремикс")
    hook, script, cta = source_remix_fields(source) if source else ("", "", "")
    target_format = payload.format or (source.platform if source else "reels")
    remix = Remix(
        user_id=user_id,
        slug=unique_remix_slug(session, title),
        source_reel_id=source.id if source else None,
        title=title,
        brief=payload.brief,
        hook=hook,
        script=script,
        cta=cta,
        thread_text=script[:500] if target_format == "threads" and len(script) <= 500 else "",
        format=target_format,
        production_stage="text" if target_format == "threads" else "script",
    )
    session.add(remix)
    session.flush()
    record_event(session, "remix.created", "remix", remix.id, {"source_reel_id": remix.source_reel_id})
    session.commit()
    session.refresh(remix)
    return remix_read(session, remix)


@router.get("/remixes/{slug}", response_model=RemixRead)
def get_remix(slug: str, session: Session = Depends(get_session), user_id: int = Depends(require_user_id)) -> RemixRead:
    remix = session.exec(select(Remix).where(Remix.slug == slug, Remix.user_id == user_id)).first()
    if not remix:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ремикс не найден")
    return remix_read(session, remix)


@router.patch("/remixes/{slug}", response_model=RemixRead)
def update_remix(slug: str, payload: RemixUpdate, session: Session = Depends(get_session), user_id: int = Depends(require_user_id)) -> RemixRead:
    remix = session.exec(select(Remix).where(Remix.slug == slug, Remix.user_id == user_id).with_for_update()).first()
    if not remix:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ремикс не найден")
    changes = payload.model_dump(exclude_unset=True)
    expected = changes.pop("expected_updated_at", None)
    current = remix.updated_at.replace(tzinfo=timezone.utc) if remix.updated_at.tzinfo is None else remix.updated_at
    if expected is not None and current != expected:
        raise HTTPException(409, "Материал изменён в другом окне. Ваш текст остаётся в редакторе; обновите данные перед повторным сохранением.")
    if changes.get("title") is not None and not changes["title"].strip():
        raise HTTPException(422, "Введите название публикации")
    target_format = changes.get("format", remix.format)
    if target_format == "threads":
        if changes.get("production_stage") in {"filming", "editing"}:
            raise HTTPException(422, "У Threads нет этапов съёмки и монтажа")
        changes["production_stage"] = "text"
    elif remix.production_stage == "text" and "production_stage" not in changes:
        changes["production_stage"] = "script"
    target_status = changes.get("status", remix.status)
    if changes.get("published_at") and target_status != "published":
        raise HTTPException(422, "Фактическую дату можно указать только у опубликованного материала")
    if target_status == "published" and remix.status != "published":
        changes["published_at"] = changes.get("published_at") or utc_now()
    elif target_status != "published":
        changes["published_at"] = None
    for key, value in changes.items():
        setattr(remix, key, value)
    remix.updated_at = utc_now()
    session.add(remix)
    record_event(session, "remix.updated", "remix", remix.id, {"fields": sorted(changes)})
    session.commit()
    session.refresh(remix)
    return remix_read(session, remix)


@router.delete("/remixes/{slug}", status_code=status.HTTP_204_NO_CONTENT)
def delete_remix(slug: str, session: Session = Depends(get_session), user_id: int = Depends(require_user_id)) -> None:
    remix = session.exec(select(Remix).where(Remix.slug == slug, Remix.user_id == user_id)).first()
    if not remix:
        raise HTTPException(404, "Черновик не найден")
    session.delete(remix)
    session.commit()


@router.post("/remixes/{slug}/derive", response_model=RemixRead, status_code=201)
def derive_remix(slug: str, payload: RemixDerive, session: Session = Depends(get_session), user_id: int = Depends(require_user_id)) -> RemixRead:
    source = session.exec(select(Remix).where(Remix.slug == slug, Remix.user_id == user_id)).first()
    if not source:
        raise HTTPException(404, "Черновик не найден")
    if payload.format == "threads" and not source.thread_text.strip():
        raise HTTPException(422, "Сначала подготовьте текст Threads")
    draft = Remix(
        user_id=user_id,
        slug=unique_remix_slug(session, source.title), source_reel_id=source.source_reel_id,
        title=source.title, brief=source.brief, hook=source.hook, script=source.script,
        cta=source.cta, thread_text=source.thread_text, format=payload.format, status="idea",
        production_stage="text" if payload.format == "threads" else "script",
    )
    session.add(draft)
    session.commit()
    session.refresh(draft)
    return remix_read(session, draft)


@router.post("/remixes/{slug}/rewrite", response_model=RemixRead)
def rewrite_remix(slug: str, confirm: bool = False, session: Session = Depends(get_session), user_id: int = Depends(require_user_id)) -> RemixRead:
    remix = session.exec(select(Remix).where(Remix.slug == slug, Remix.user_id == user_id).with_for_update()).first()
    if not remix:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ремикс не найден")

    if not confirm:
        raise HTTPException(409, "Подтвердите замену вашей редакции исходным переводом")
    if remix.source_reel and remix.source_reel.user_id == user_id:
        if not source_remix_fields(remix.source_reel)[1]:
            raise HTTPException(409, "Перевод ещё не готов; ваша редакция сохранена")
        remix.hook, remix.script, remix.cta = source_remix_fields(remix.source_reel)
    else:
        raise HTTPException(409, "У самостоятельной идеи нет исходного перевода")
    remix.updated_at = utc_now()
    session.add(remix)
    record_event(session, "remix.rewritten", "remix", remix.id)
    session.commit()
    session.refresh(remix)
    return remix_read(session, remix)


@router.post("/remixes/{slug}/prepare-thread", response_model=RemixRead)
def prepare_thread(slug: str, confirm: bool = False, session: Session = Depends(get_session), user_id: int = Depends(require_user_id)) -> RemixRead:
    remix = session.exec(select(Remix).where(Remix.slug == slug, Remix.user_id == user_id).with_for_update()).first()
    if not remix:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ремикс не найден")
    if remix.thread_text.strip() and not confirm:
        raise HTTPException(409, "Подтвердите замену существующего текста Threads")
    parts = [value.strip() for value in (remix.hook, remix.script, remix.cta) if value.strip()]
    text_parts = []
    for part in parts:
        if part not in "\n\n".join(text_parts):
            if text_parts and part.startswith(text_parts[-1]):
                text_parts[-1] = part
            else:
                text_parts.append(part)
    text = "\n\n".join(text_parts)
    if not text:
        raise HTTPException(422, "Сначала добавьте свой хук или сценарий")
    # Deterministic preparation, not an invented AI rewrite. User can edit the excerpt.
    remix.thread_text = text if len(text) <= 500 else text[:499].rstrip() + "…"
    remix.updated_at = utc_now()
    session.add(remix)
    record_event(session, "remix.thread_ready", "remix", remix.id)
    session.commit()
    session.refresh(remix)
    return remix_read(session, remix)


@router.get("/imports", response_model=list[ImportJobRead])
def list_imports(session: Session = Depends(get_session), user_id: int = Depends(require_user_id)) -> list[ImportJobRead]:
    jobs = session.exec(select(ImportJob).where(ImportJob.user_id == user_id).order_by(ImportJob.created_at.desc()).limit(25)).all()
    return [import_read(session, job) for job in jobs]


@router.post("/imports/{job_id}/cancel", response_model=ImportJobRead)
def cancel_import(
    job_id: int,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    user_id: int = Depends(require_user_id),
) -> ImportJobRead:
    trial_user(session, user_id)
    job = session.get(ImportJob, job_id)
    if not job or job.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Задача импорта не найдена")
    if job.status == "cancelled":
        return import_read(session, job)
    if job.status not in ACTIVE_IMPORT_STATUSES:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Этот импорт уже завершён")

    now = utc_now()
    entry = {
        "at": now.isoformat(),
        "stage": "cancelled",
        "message": "Импорт остановлен пользователем",
        "details": {"actor_run_id": job.actor_run_id},
    }
    job.status = "cancelled"
    job.stage = "cancelled"
    job.stage_message = "Импорт остановлен пользователем"
    job.error_message = None
    job.completed_at = now
    job.updated_at = now
    job.debug_log = [*(job.debug_log or []), entry][-100:]
    session.add(job)
    record_event(session, "import.cancelled", "import_job", job.id, entry)
    session.commit()
    session.refresh(job)

    token = (settings.apify_token or "").strip()
    if job.actor_run_id and token:
        try:
            aborted = ApifyClient(token).run(job.actor_run_id).abort(gracefully=False)
            abort_status = (aborted or {}).get("status", "ABORT_REQUESTED")
            abort_entry = {
                "at": utc_now().isoformat(),
                "stage": "cancelled",
                "message": "Apify подтвердил остановку запуска",
                "details": {"actor_run_id": job.actor_run_id, "apify_status": abort_status},
            }
        except Exception as error:
            safe_message = str(error).replace(token, "[redacted]")[:1000]
            abort_entry = {
                "at": utc_now().isoformat(),
                "stage": "cancelled",
                "message": "Задача отменена в приложении; Apify уже мог завершить запуск",
                "details": {"actor_run_id": job.actor_run_id, "abort_error": safe_message},
            }
        job.debug_log = [*(job.debug_log or []), abort_entry][-100:]
        job.updated_at = utc_now()
        session.add(job)
        record_event(session, "import.apify_abort", "import_job", job.id, abort_entry)
        session.commit()
        session.refresh(job)

    return import_read(session, job)


def _translation_overview(session: Session, settings: Settings, user_id: int) -> TranslationOverviewRead:
    counts = translation_counts(session, user_id)
    batches = session.exec(
        select(TranslationBatch).where(TranslationBatch.user_id == user_id).order_by(TranslationBatch.created_at.desc()).limit(20)
    ).all()
    active = any(batch.status in ACTIVE_TRANSLATION_STATUSES for batch in batches)
    return TranslationOverviewRead(
        summary=TranslationSummaryRead(
            **counts,
            active=active,
            configured=translation_ready(settings),
            model=translation_model(settings),
            reasoning_effort=translation_effort(settings),
            batch_size=settings.translation_batch_size,
        ),
        batches=[TranslationBatchRead.model_validate(batch) for batch in batches],
    )


@router.get("/translations", response_model=TranslationOverviewRead)
def list_translations(
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    user_id: int = Depends(require_user_id),
) -> TranslationOverviewRead:
    return _translation_overview(session, settings, user_id)


@router.post("/translations/backfill", response_model=TranslationOverviewRead, status_code=status.HTTP_202_ACCEPTED)
def start_translation_backfill(
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    user_id: int = Depends(require_user_id),
) -> TranslationOverviewRead:
    if not translation_ready(settings):
        raise HTTPException(503, "AI-перевод пока не подключён. Исходники и ручное редактирование доступны.")
    active = session.exec(
        select(TranslationBatch.id).where(TranslationBatch.user_id == user_id, TranslationBatch.status.in_(ACTIVE_TRANSLATION_STATUSES)).limit(1)
    ).first()
    if active is None:
        background_tasks.add_task(run_translation_backfill, user_id=user_id)
    return _translation_overview(session, settings, user_id)


@router.post("/imports", response_model=ImportJobRead, status_code=status.HTTP_202_ACCEPTED)
def create_import(
    payload: ImportCreate,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    user_id: int = Depends(require_user_id),
) -> ImportJobRead:
    competitor = session.get(Competitor, payload.competitor_id)
    if not competitor or competitor.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Конкурент не найден")
    if competitor.handle == "@pantela.evgeny":
        raise HTTPException(403, "Этот аккаунт не обновляется без отдельного запроса владельца")
    active_job = session.exec(
        select(ImportJob)
        .where(ImportJob.competitor_id == competitor.id, ImportJob.user_id == user_id)
        .where(ImportJob.status.in_(ACTIVE_IMPORT_STATUSES))
        .order_by(ImportJob.created_at.desc())
    ).first()
    if active_job:
        return import_read(session, active_job)

    _check_import_budget(session, user_id, settings)
    active_job = session.exec(
        select(ImportJob).where(ImportJob.competitor_id == competitor.id, ImportJob.user_id == user_id,
                                ImportJob.status.in_(ACTIVE_IMPORT_STATUSES))
        .order_by(ImportJob.created_at.desc())
    ).first()
    if active_job:
        return import_read(session, active_job)

    created_at = utc_now()
    trial_limit = reserve_trial(session, user_id, competitor.platform)
    initial_status = "queued" if settings.apify_token else "waiting_for_token"
    job = ImportJob(
        user_id=user_id,
        competitor_id=competitor.id,
        requested_count=trial_limit if trial_limit is not None else min(payload.requested_count, settings.apify_import_limit, 20),
        trial_reels_limit=trial_limit,
        status=initial_status,
        stage="queued" if settings.apify_token else "waiting_for_token",
        stage_message="Задача поставлена в очередь" if settings.apify_token else "Для запуска нужен Apify token",
        progress_current=2,
        progress_total=8,
        debug_log=[
            {
                "at": created_at.isoformat(),
                "stage": "database",
                "message": "Конкурент уже находится в PostgreSQL",
                "details": {"handle": competitor.handle},
            },
            {
                "at": created_at.isoformat(),
                "stage": "queued" if settings.apify_token else "waiting_for_token",
                "message": "Задача поставлена в очередь" if settings.apify_token else "Ожидаем Apify token",
            },
        ],
    )
    session.add(job)
    session.flush()
    record_event(session, "import.created", "import_job", job.id, {"status": job.status})
    session.commit()
    session.refresh(job)
    if settings.apify_token:
        background_tasks.add_task(run_apify_import, job.id)
    return import_read(session, job)
