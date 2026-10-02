import re
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from apify_client import ApifyClient
from sqlalchemy import text
from sqlmodel import Session, select

from .config import Settings, get_settings
from .database import engine
from .models import Competitor, ImportJob, Reel
from .trial import trial_user
from .live_billing import active_package
from .services import mark_russian_source_ready, record_event, utc_now


HASHTAG_PATTERN = re.compile(r"#([\w.]+)", re.UNICODE)
ACTIVE_IMPORT_STATUSES = {"queued", "running"}
THUMBNAIL_MAX_BYTES = 5 * 1024 * 1024


class ImportCancelled(Exception):
    """Raised inside the worker when a user has cancelled the import."""


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _transcript_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("text", "transcript", "content"):
            text = _transcript_text(value.get(key))
            if text:
                return text
        segments = value.get("segments")
        if isinstance(segments, list):
            return _transcript_text(segments)
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                part = _transcript_text(item.get("text") or item.get("content"))
            else:
                part = _transcript_text(item)
            if part:
                parts.append(part)
        return " ".join(parts).strip()
    return ""


def _count(item: dict[str, Any], *keys: str) -> int:
    for key in keys:
        value = item.get(key)
        if value is None or isinstance(value, bool):
            continue
        try:
            return max(0, int(float(str(value).replace(",", ""))))
        except (TypeError, ValueError):
            continue
    return 0


def _optional_count(item: dict[str, Any], *keys: str) -> int | None:
    if not any(item.get(key) is not None for key in keys):
        return None
    return _count(item, *keys)


def _timestamp(value: Any) -> datetime | None:
    if isinstance(value, (int, float)):
        seconds = float(value)
        if seconds > 10_000_000_000:
            seconds /= 1000
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    if isinstance(value, str) and value.strip():
        candidate = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(candidate)
            return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
        except ValueError:
            return None
    return None


def _thumbnail_url(item: dict[str, Any]) -> str | None:
    for key in ("displayUrl", "thumbnailUrl", "imageUrl"):
        value = _text(item.get(key))
        if value:
            return value
    images = item.get("images")
    if isinstance(images, list) and images:
        first = images[0]
        if isinstance(first, str):
            return first
        if isinstance(first, dict):
            return _text(first.get("url")) or None
    return None


def _owner_value(item: dict[str, Any], key: str) -> str:
    direct = _text(item.get(key))
    if direct:
        return direct
    owner = item.get("owner")
    if isinstance(owner, dict):
        snake_key = re.sub(r"(?<!^)(?=[A-Z])", "_", key).lower()
        return _text(owner.get(key)) or _text(owner.get(snake_key))
    return ""


def reel_values(item: dict[str, Any], competitor: Competitor) -> dict[str, Any] | None:
    external_id = str(item.get("id") or item.get("shortCode") or item.get("shortcode") or "").strip()
    if not external_id:
        return None

    caption = _text(item.get("caption"))
    transcript = _transcript_text(item.get("transcript")) or None
    short_code = _text(item.get("shortCode")) or _text(item.get("shortcode")) or external_id
    first_line = next((line.strip() for line in caption.splitlines() if line.strip()), "")
    title = (first_line or f"Reel {short_code}")[:255]
    hook = first_line or transcript or title

    raw_topics = item.get("hashtags")
    if isinstance(raw_topics, list):
        topics = [str(topic).lstrip("#").strip() for topic in raw_topics if str(topic).strip()]
    else:
        topics = HASHTAG_PATTERN.findall(caption)
    topics = list(dict.fromkeys(topics))[:30]

    owner_username = _owner_value(item, "ownerUsername") or competitor.handle.lstrip("@")
    author = owner_username if owner_username.startswith("@") else f"@{owner_username}"
    original_url = _text(item.get("url")) or _text(item.get("inputUrl")) or None
    published_at = _timestamp(item.get("timestamp") or item.get("takenAt") or item.get("taken_at"))
    duration = _optional_count(item, "videoDuration", "duration", "durationSeconds")
    search_text = " ".join([title, caption, transcript or "", author, *topics]).lower()

    return {
        "external_id": external_id,
        "title": title,
        "hook": hook,
        "caption": caption,
        "transcript": transcript,
        "topics": topics,
        "search_text": search_text,
        "author": author,
        "views": _optional_count(item, "videoPlayCount", "videoViewCount", "viewCount", "viewsCount", "views"),
        "likes_count": _optional_count(item, "likesCount", "likeCount", "likes"),
        "comments_count": _optional_count(item, "commentsCount", "commentCount", "comments"),
        "shares_count": _optional_count(item, "sharesCount", "shareCount", "shares"),
        "duration_seconds": duration,
        "published_at": published_at,
        "original_url": original_url,
        "thumbnail_url": _thumbnail_url(item),
        "media_path": None,
        "thumb_variant": (sum(ord(character) for character in short_code) % 4) + 1,
    }


def thread_values(item: dict[str, Any], competitor: Competitor) -> dict[str, Any] | None:
    """webdata_labs/threads-scraper post output; no video processing."""
    body = _text(item.get("text"))
    post_id = str(item.get("postId") or item.get("code") or "").strip()
    if item.get("type") != "post" or not body or not post_id:
        return None
    username = _text(item.get("username")).lstrip("@") or competitor.handle.lstrip("@")
    if username.lower() != competitor.handle.lstrip("@").lower():
        return None
    topics = [str(value).lstrip("#") for value in (item.get("hashtags") or [])][:30]
    original_url = _text(item.get("url"))
    parsed = urlsplit(original_url)
    if parsed.scheme != "https" or parsed.hostname not in {"threads.com", "www.threads.com", "threads.net", "www.threads.net"}:
        return None
    return {
        "platform": "threads", "external_id": f"threads:{post_id}",
        "title": body.splitlines()[0][:255], "hook": body[:4000], "caption": body,
        "transcript": None, "author": f"@{username}", "topics": topics,
        "search_text": " ".join([body, username, *topics]).lower(),
        "published_at": _timestamp(item.get("date")), "original_url": original_url,
        "views": None, "duration_seconds": None,
        "likes_count": _optional_count(item, "likeCount"),
        "comments_count": _optional_count(item, "replyCount"),
        "shares_count": _optional_count(item, "repostCount"),
        "thumbnail_url": None, "media_path": None,
    }


def _avatar_url(item: dict[str, Any]) -> str | None:
    return (
        _owner_value(item, "ownerProfilePicUrl")
        or _owner_value(item, "profilePicUrlHD")
        or _owner_value(item, "profilePicUrlHd")
        or _owner_value(item, "profilePicUrl")
        or _text(item.get("profile_pic_url_hd"))
        or _text(item.get("profile_pic_url"))
        or None
    )


def _session_factory() -> Session:
    return Session(engine)


def _safe_error(error: Exception, token: str) -> str:
    message = str(error).replace(token, "[redacted]") if token else str(error)
    return message[:2000] or error.__class__.__name__


def _cache_image(source_url: str | None, relative_path: Path, media_root: Path) -> str | None:
    if not source_url:
        return None
    destination = Path(media_root) / relative_path
    if destination.is_file() and destination.stat().st_size > 0:
        return f"/media/{relative_path.as_posix()}"

    parsed_url = urlsplit(source_url)
    fallback_url = urlunsplit((
        parsed_url.scheme or "https",
        "scontent-waw2-1.cdninstagram.com",
        parsed_url.path,
        parsed_url.query,
        parsed_url.fragment,
    ))
    candidates = [source_url]
    if parsed_url.netloc != "scontent-waw2-1.cdninstagram.com":
        candidates.append(fallback_url)

    for candidate in candidates:
        request = Request(
            candidate,
            headers={
                "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                "Referer": "https://www.instagram.com/",
                "User-Agent": "Mozilla/5.0 (compatible; AIProducer/1.0)",
            },
        )
        try:
            with urlopen(request, timeout=10) as response:
                content_type = response.headers.get_content_type()
                if not content_type.startswith("image/"):
                    continue
                payload = response.read(THUMBNAIL_MAX_BYTES + 1)
            if not payload or len(payload) > THUMBNAIL_MAX_BYTES:
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_suffix(".tmp")
            temporary.write_bytes(payload)
            temporary.replace(destination)
            return f"/media/{relative_path.as_posix()}"
        except (HTTPError, URLError, OSError, TimeoutError, ValueError):
            continue
    return None


def cache_thumbnail(thumbnail_url: str | None, external_id: str, media_root: Path) -> str | None:
    safe_id = re.sub(r"[^A-Za-z0-9._-]", "-", external_id)[:180]
    return _cache_image(thumbnail_url, Path("thumbnails") / f"{safe_id}.jpg", media_root)


def cache_avatar(avatar_url: str | None, handle: str, media_root: Path) -> str | None:
    safe_handle = re.sub(r"[^A-Za-z0-9._-]", "-", handle.lstrip("@"))[:120]
    return _cache_image(avatar_url, Path("avatars") / f"{safe_handle}.jpg", media_root)


def fetch_profile_avatars(
    client: Any,
    usernames: list[str],
    settings: Settings,
) -> dict[str, tuple[str | None, dict[str, Any]]]:
    clean_usernames = list(dict.fromkeys(username.lstrip("@").lower() for username in usernames if username.strip()))
    if not clean_usernames:
        return {}
    run = client.actor(settings.apify_profile_actor_id).call(
        run_input={"usernames": clean_usernames, "includeAboutSection": False},
        max_items=len(clean_usernames),
        max_total_charge_usd=Decimal(str(settings.apify_profile_max_charge_usd)),
        restart_on_error=False,
        timeout_secs=180,
    )
    if not run or run.get("status") != "SUCCEEDED" or not run.get("defaultDatasetId"):
        return {
            username: (None, {"status": (run or {}).get("status", "NO_RESULT")})
            for username in clean_usernames
        }
    dataset_id = run["defaultDatasetId"]
    page = client.dataset(dataset_id).list_items(limit=len(clean_usernames))
    results: dict[str, tuple[str | None, dict[str, Any]]] = {}
    for profile in (item for item in page.items if isinstance(item, dict)):
        username = _text(profile.get("username") or profile.get("ownerUsername")).lstrip("@").lower()
        if not username:
            continue
        results[username] = (
            _avatar_url(profile),
            {
                "actor_run_id": run.get("id"),
                "dataset_id": dataset_id,
                "profile_found": True,
            },
        )
    for username in clean_usernames:
        results.setdefault(
            username,
            (
                None,
                {
                    "actor_run_id": run.get("id"),
                    "dataset_id": dataset_id,
                    "profile_found": False,
                },
            ),
        )
    return results


def fetch_profile_avatar(client: Any, username: str, settings: Settings) -> tuple[str | None, dict[str, Any]]:
    clean_username = username.lstrip("@").lower()
    return fetch_profile_avatars(client, [clean_username], settings)[clean_username]


def _set_job_stage(
    session: Session,
    job: ImportJob,
    stage: str,
    message: str,
    current: int,
    *,
    status: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    database_status = session.connection().execute(
        text("SELECT status FROM import_jobs WHERE id = :job_id"),
        {"job_id": job.id},
    ).scalar_one_or_none()
    if database_status == "cancelled" and status != "cancelled":
        raise ImportCancelled
    now = utc_now()
    entry: dict[str, Any] = {
        "at": now.isoformat(),
        "stage": stage,
        "message": message,
    }
    if details:
        entry["details"] = details
    job.stage = stage
    job.stage_message = message
    job.progress_current = current
    if status:
        job.status = status
    job.updated_at = now
    job.debug_log = [*(job.debug_log or []), entry][-100:]
    session.add(job)
    record_event(session, "import.stage", "import_job", job.id, entry)
    session.commit()


def _raise_if_cancelled(session: Session, job: ImportJob) -> None:
    database_status = session.connection().execute(
        text("SELECT status FROM import_jobs WHERE id = :job_id"),
        {"job_id": job.id},
    ).scalar_one_or_none()
    if database_status in {None, "cancelled"}:
        raise ImportCancelled


def run_apify_import(
    job_id: int,
    *,
    settings_override: Settings | None = None,
    session_factory: Callable[[], Session] | None = None,
    client_factory: Callable[[str], Any] = ApifyClient,
    thumbnail_cache: Callable[[str | None, str, Path], str | None] = cache_thumbnail,
    profile_fetcher: Callable[[Any, str, Settings], tuple[str | None, dict[str, Any]]] = fetch_profile_avatar,
    avatar_cache: Callable[[str | None, str, Path], str | None] = cache_avatar,
) -> None:
    settings = settings_override or get_settings()
    create_session = session_factory or _session_factory
    token = (settings.apify_token or "").strip()

    with create_session() as session:
        job = session.get(ImportJob, job_id)
        if not job:
            return
        if job.status == "cancelled":
            return
        competitor = session.get(Competitor, job.competitor_id)
        if not competitor or competitor.user_id != job.user_id:
            job.error_message = "Конкурент не найден"
            job.completed_at = utc_now()
            _set_job_stage(session, job, "failed", job.error_message, job.progress_total, status="failed")
            return
        if competitor.handle == "@pantela.evgeny":
            job.error_message = "Этот аккаунт не обновляется без отдельного запроса владельца"
            job.completed_at = utc_now()
            _set_job_stage(session, job, "failed", job.error_message, job.progress_total, status="failed")
            return
        if not token:
            job.error_message = None
            _set_job_stage(
                session,
                job,
                "waiting_for_token",
                "Конкурент сохранён. Для запуска нужен Apify token",
                2,
                status="waiting_for_token",
            )
            return

        job.started_at = utc_now()
        job.error_message = None
        instagram_username = competitor.handle.lstrip("@")
        is_threads = competitor.platform == "threads"
        actor_id = settings.apify_threads_actor_id if is_threads else settings.apify_actor_id
        requested_count = min(job.requested_count, settings.apify_import_limit, 20)
        trial_limit = job.trial_reels_limit
        import_user_id = job.user_id
        scan_count = min(settings.apify_import_limit, 20) if trial_limit is not None else requested_count
        current_avatar_url = competitor.avatar_url
        _set_job_stage(
            session,
            job,
            "apify",
            "Apify получил задачу",
            3,
            status="running",
            details={"requested_count": requested_count, "actor": actor_id},
        )

    try:
        client = client_factory(token)
        actor_input = {
            "username": [instagram_username],
            "resultsLimit": scan_count,
            "skipPinnedPosts": trial_limit is None,
            "skipTrialReels": False,
            "includeSharesCount": False,
            "includeTranscript": True,
            "includeDownloadedVideo": False,
        }
        if is_threads:
            actor_input = {"mode": "posts", "usernames": [instagram_username], "maxPosts": requested_count, "includeProfile": False}
        with create_session() as session:
            job = session.get(ImportJob, job_id)
            if not job:
                return
            _raise_if_cancelled(session, job)

        run = client.actor(actor_id).start(
            run_input=actor_input,
            max_items=scan_count,
            max_total_charge_usd=Decimal(str(settings.apify_threads_max_charge_usd if is_threads else settings.apify_max_charge_usd)),
            restart_on_error=False,
            timeout_secs=300,
        )
        if not run:
            raise RuntimeError("Apify не вернул данные запуска")
        actor_run_id = run.get("id")
        if not actor_run_id:
            raise RuntimeError("Apify не вернул идентификатор запуска")
        run_client = client.run(actor_run_id)

        with create_session() as session:
            job = session.get(ImportJob, job_id)
            if not job:
                run_client.abort(gracefully=False)
                return
            job.actor_run_id = actor_run_id
            session.add(job)
            session.commit()
            session.refresh(job)
            if job.status == "cancelled":
                run_client.abort(gracefully=False)
                return
            _set_job_stage(
                session,
                job,
                "fetching" if is_threads else "transcription",
                "Apify получает тексты и реакции Threads" if is_threads else "Apify загружает Reels и расшифровывает аудио",
                4,
                status="running",
                details={"include_transcript": not is_threads, "actor_run_id": actor_run_id},
            )

        finished_run = run_client.wait_for_finish(wait_secs=300)
        with create_session() as session:
            job = session.get(ImportJob, job_id)
            if not job or job.status == "cancelled":
                return
        if not finished_run:
            raise RuntimeError("Apify не вернул итоговый статус запуска")
        if finished_run.get("status") != "SUCCEEDED":
            raise RuntimeError(f"Apify завершил запуск со статусом {finished_run.get('status', 'UNKNOWN')}")
        dataset_id = finished_run.get("defaultDatasetId")
        if not dataset_id:
            raise RuntimeError("Apify не вернул dataset")
        page = client.dataset(dataset_id).list_items(limit=scan_count)
        raw_items = [item for item in page.items if isinstance(item, dict)]

        with create_session() as session:
            job = session.get(ImportJob, job_id)
            if not job:
                return
            job.dataset_id = dataset_id
            _set_job_stage(
                session,
                job,
                "results",
                f"Apify вернул {len(raw_items)} записей",
                5,
                status="running",
                details={"actor_run_id": job.actor_run_id, "dataset_id": dataset_id, "raw_count": len(raw_items)},
            )

        profile_avatar_url = _avatar_url(raw_items[0]) if raw_items else None
        profile_details: dict[str, Any] = {}
        profile_error: str | None = None
        with create_session() as session:
            job = session.get(ImportJob, job_id)
            if not job:
                return
            _raise_if_cancelled(session, job)
            _set_job_stage(
                session,
                job,
                "avatar",
                "Проверяем текстовые публикации" if is_threads else "Проверяем и сохраняем аватар профиля",
                6,
                status="running",
                details={"cached_before_import": bool(current_avatar_url)},
            )

        if not is_threads and not current_avatar_url and not profile_avatar_url:
            try:
                profile_avatar_url, profile_details = profile_fetcher(client, instagram_username, settings)
            except Exception as error:
                profile_error = _safe_error(error, token)
        with create_session() as session:
            job = session.get(ImportJob, job_id)
            if not job:
                return
            _raise_if_cancelled(session, job)
        cached_avatar = None if is_threads else avatar_cache(
            profile_avatar_url or current_avatar_url,
            f"{job.user_id}-{instagram_username}",
            settings.media_root,
        )

        with create_session() as session:
            job = session.get(ImportJob, job_id)
            if not job:
                return
            competitor = session.get(Competitor, job.competitor_id)
            if not competitor or competitor.user_id != job.user_id:
                raise RuntimeError("Конкурент удалён во время импорта")

            normalizer = thread_values if is_threads else reel_values
            normalized = list({values["external_id"]: values for item in raw_items if (values := normalizer(item, competitor))}.values())
            normalized.sort(key=lambda values: values["published_at"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
            if trial_limit is not None:
                existing_ids = set(session.exec(select(Reel.external_id).where(Reel.user_id == job.user_id)).all())
                normalized = [values for values in normalized if values["external_id"] not in existing_ids]
                normalized.sort(key=lambda values: (values.get("views") or 0, values.get("likes_count") or 0), reverse=True)
            normalized = normalized[:requested_count]
            if not normalized:
                raise RuntimeError("Apify не вернул доступных публикаций этого аккаунта. Проверьте имя, публичность профиля и журнал загрузки.")

            _set_job_stage(
                session,
                job,
                "saving",
                "Сохраняем материалы и показатели",
                7,
                status="running",
                details={
                    "normalized_count": len(normalized),
                    "avatar_cached": bool(cached_avatar),
                    "avatar_error": profile_error,
                    **profile_details,
                },
            )

            cached_thumbnail_count = 0
            quota_user = trial_user(session, job.user_id)
            # Serialize cancellation/deletion with saving + quota consumption.
            _raise_if_cancelled(session, job)
            if trial_limit is not None:
                paid = active_package(session, job.user_id) if job.payment_id else None
                if job.payment_id and (paid is None or paid.id != job.payment_id):
                    raise RuntimeError("Оплаченный период завершён или платёж возвращён. Новые материалы не сохранены.")
                remaining = max(0, paid.quota-paid.used) if paid else max(0, (quota_user.trial_reels_limit or 0) - quota_user.trial_reels_used)
                normalized = normalized[:min(trial_limit, remaining)]
                if not normalized:
                    raise RuntimeError("Лимит материалов исчерпан.")
            imported_ids = []
            new_count = 0
            for values in normalized:
                _raise_if_cancelled(session, job)
                cached_thumbnail = None if is_threads else thumbnail_cache(
                    values["thumbnail_url"],
                    f"{job.user_id}-{values['external_id']}",
                    settings.media_root,
                )
                if cached_thumbnail:
                    values["media_path"] = cached_thumbnail
                    cached_thumbnail_count += 1
                reel = session.exec(select(Reel).where(Reel.user_id == job.user_id, Reel.external_id == values["external_id"])).first()
                if reel is None:
                    reel = Reel(user_id=job.user_id, competitor_id=competitor.id, **values)
                    new_count += 1
                else:
                    previous_transcript = reel.caption if is_threads else reel.transcript
                    reel.competitor_id = competitor.id
                    for field, value in values.items():
                        if field == "transcript" and value is None and reel.transcript:
                            continue
                        if field == "media_path" and value is None and reel.media_path:
                            continue
                        setattr(reel, field, value)
                    incoming_text = values.get("caption") if is_threads else values.get("transcript")
                    if incoming_text and incoming_text != previous_transcript:
                        reel.translated_hook = None
                        reel.translated_script = None
                        reel.translated_cta = None
                        reel.translation_status = "pending"
                        reel.translation_error = None
                        reel.translation_source_hash = None
                        reel.translation_model = None
                        reel.translation_reasoning_effort = None
                        reel.translated_at = None
                    reel.updated_at = utc_now()
                session.add(reel)
                session.flush()
                imported_ids.append(reel.id)

                mark_russian_source_ready(reel)
                session.add(reel)

                # Source refresh never overwrites any user's remix, including empty fields.

            _raise_if_cancelled(session, job)
            imported_at = utc_now()
            if trial_limit is not None:
                if job.payment_id:
                    paid.used += new_count
                    session.add(paid)
                else:
                    quota_user.trial_reels_used += new_count
                    session.add(quota_user)
            competitor.avatar_url = cached_avatar or profile_avatar_url or competitor.avatar_url
            competitor.last_import_at = imported_at
            competitor.updated_at = imported_at
            job.status = "completed"
            job.imported_count = len(normalized)
            job.completed_at = imported_at
            job.error_message = None
            missing_count = max(0, requested_count - len(normalized))
            final_stage = "partial" if missing_count else "completed"
            final_message = (
                f"Apify вернул {len(normalized)} доступных публикаций из {requested_count}. "
                f"Ещё {missing_count} не получены от источника."
                if missing_count
                else f"Сохранено публикаций: {len(normalized)}"
            )
            job.result_summary = {
                "selection": "most_viewed_in_recent_sample" if trial_limit is not None else "recent",
                "scanned_count": len(raw_items),
                "requested_count": requested_count,
                "raw_count": len(raw_items),
                "normalized_count": len(normalized),
                "new_count": new_count,
                "updated_count": len(normalized) - new_count,
                "rejected_count": max(0, len(raw_items) - len(normalized)),
                "missing_count": missing_count,
                "transcript_count": sum(1 for values in normalized if values.get("transcript")),
                "thumbnails_cached": cached_thumbnail_count,
                "avatar_cached": bool(cached_avatar),
                "shortfall_reason": (
                    "При сохранении потерь нет. Источник мог вернуть меньше публикаций из-за ограничений публичного доступа или количества доступных записей."
                    if missing_count
                    else None
                ),
            }
            session.add(competitor)
            record_event(
                session,
                "import.completed",
                "import_job",
                job.id,
                {"imported_count": len(normalized), "actor_run_id": job.actor_run_id},
            )
            _set_job_stage(
                session,
                job,
                final_stage,
                final_message,
                8,
                status="completed",
                details=job.result_summary,
            )
        if settings.translation_auto_start:
            from .translation import run_translation_backfill

            try:
                run_translation_backfill(settings_override=settings, session_factory=create_session, only_ids=imported_ids, user_id=import_user_id)
            except Exception as translation_error:
                with create_session() as session:
                    record_event(
                        session,
                        "translation.autostart_failed",
                        "import_job",
                        job_id,
                        {"error": str(translation_error)[-4000:]},
                    )
                    session.commit()
    except ImportCancelled:
        return
    except Exception as error:
        with create_session() as session:
            job = session.get(ImportJob, job_id)
            if not job:
                return
            if job.status == "cancelled":
                return
            job.error_message = _safe_error(error, token)
            job.completed_at = utc_now()
            record_event(session, "import.failed", "import_job", job.id, {"error": job.error_message})
            _set_job_stage(
                session,
                job,
                "failed",
                job.error_message,
                job.progress_total,
                status="failed",
                details={"error_type": error.__class__.__name__},
            )
