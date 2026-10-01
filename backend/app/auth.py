"""Telegram login, opaque server sessions, and small shared security helpers."""

import asyncio
import hashlib
import hmac
import io
import json
import logging
import os
import re
import secrets
import threading
from datetime import datetime, timedelta, timezone
from urllib.request import Request as UrlRequest, urlopen

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import text
from sqlmodel import Session, select
from starlette.concurrency import run_in_threadpool

from .config import Settings, get_settings
from .database import engine, get_session
from .models import AuthChallenge, AuthIdentity, LoginSession, TelegramUpdate, User, utc_now


router = APIRouter(prefix="/api/auth")
webhook_router = APIRouter(prefix="/api/telegram")
SESSION_COOKIE = "__Host-hype_session"
CHALLENGE_COOKIE = "__Host-hype_challenge"
CSRF_COOKIE = "__Host-hype_csrf"
CHALLENGE_RE = re.compile(r"^[A-Za-z0-9_-]{43}$")


class ChallengeRequest(BaseModel):
    return_to: str = "/today"


class ChallengeFinish(BaseModel):
    challenge_id: str


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str = Field(min_length=1, max_length=80)

    @field_validator("display_name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value or any(ord(char) < 32 for char in value):
            raise ValueError("Введите имя")
        return value


def _configured(settings: Settings) -> None:
    if not (settings.public_origin.startswith("https://") and settings.telegram_bot_token
            and settings.telegram_bot_username and len(settings.auth_code_secret) >= 32):
        raise HTTPException(503, "Вход через Telegram ещё не настроен")


def _mac(settings: Settings, value: str) -> str:
    return hmac.new(settings.auth_code_secret.encode(), value.encode(), hashlib.sha256).hexdigest()


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _ip_hash(request: Request, settings: Settings) -> str:
    # Use the transport peer, never an untrusted client-supplied forwarding header.
    address = request.client.host if request.client else "unknown"
    return _mac(settings, f"ip:{address}")


def _rate_limit(session: Session, settings: Settings, key: str, maximum: int, seconds: int) -> None:
    now = utc_now()
    with engine.begin() as connection:
        count = connection.execute(text("""
        INSERT INTO auth_rate_limits (key_hash, count, window_started_at)
        VALUES (:key_hash, 1, :now)
        ON CONFLICT (key_hash) DO UPDATE SET
            count = CASE WHEN auth_rate_limits.window_started_at < :cutoff
                         THEN 1 ELSE auth_rate_limits.count + 1 END,
            window_started_at = CASE WHEN auth_rate_limits.window_started_at < :cutoff
                                     THEN :now ELSE auth_rate_limits.window_started_at END
        RETURNING count
    """), {"key_hash": _mac(settings, key), "now": now,
           "cutoff": now - timedelta(seconds=seconds)}).scalar_one()
    if count > maximum:
        raise HTTPException(429, "Слишком много попыток. Попробуйте позже")


def _safe_return(value: str) -> str:
    if not value.startswith("/") or value.startswith("//") or "\\" in value or any(ord(c) < 32 for c in value):
        return "/today"
    path = value.split("?", 1)[0]
    if path in {"/today", "/library", "/content-plan", "/competitors", "/account"}:
        return value[:512]
    if re.fullmatch(r"/remixes/[a-zA-Z0-9_-]{1,255}", path):
        return value[:512]
    return "/today"


def _browser_challenge(request: Request, challenge: AuthChallenge) -> None:
    value = request.cookies.get(CHALLENGE_COOKIE, "")
    challenge_id, separator, secret = value.partition(".")
    if not separator or challenge_id != challenge.id or not hmac.compare_digest(_digest(secret), challenge.browser_secret_hash):
        raise HTTPException(403, "Запрос входа принадлежит другому браузеру")


def _telegram(method: str, payload: dict, settings: Settings) -> None:
    data = json.dumps(payload).encode()
    request = UrlRequest(
        f"https://api.telegram.org/bot{settings.telegram_bot_token}/{method}",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=10) as response:
            response.read(2048)
    except Exception:
        # Exception text may contain the Bot API URL and therefore the token.
        logging.warning("Telegram API request failed")


def _telegram_result(method: str, payload: dict, settings: Settings, timeout: int = 6) -> dict | list | bool | None:
    request = UrlRequest(
        f"https://api.telegram.org/bot{settings.telegram_bot_token}/{method}",
        data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            value = json.loads(response.read(1_000_001))
        return value.get("result") if value.get("ok") else None
    except Exception:
        return None


def _avatar_format(content: bytes) -> str | None:
    if content.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "webp"
    return None


def _refresh_avatar(user_id: int, telegram_id: int, settings: Settings) -> None:
    """Best-effort avatar update after the login response has been sent."""
    with Session(engine) as session:
        user = session.get(User, user_id)
        if not user or user.avatar_edited:
            return
    profile = _telegram_result("getUserProfilePhotos", {"user_id": telegram_id, "limit": 1}, settings)
    photos = profile.get("photos") if isinstance(profile, dict) else None
    if not photos or not photos[0]:
        return
    file_id = photos[0][-1].get("file_id")
    if not isinstance(file_id, str):
        return
    file_info = _telegram_result("getFile", {"file_id": file_id}, settings)
    remote_path = file_info.get("file_path") if isinstance(file_info, dict) else None
    if not isinstance(remote_path, str) or not remote_path.startswith("photos/"):
        return
    request = UrlRequest(f"https://api.telegram.org/file/bot{settings.telegram_bot_token}/{remote_path}")
    try:
        with urlopen(request, timeout=8) as response:
            if int(response.headers.get("Content-Length", "0")) > 1_000_000:
                return
            content = response.read(1_000_001)
        if len(content) > 1_000_000:
            return
        extension = _avatar_format(content)
        if not extension:
            return
        destination = settings.media_root / "avatars" / str(user_id)
        destination.mkdir(parents=True, exist_ok=True)
        temporary = destination / (secrets.token_hex(12) + ".tmp")
        temporary.write_bytes(content)
        target = destination / f"telegram.{extension}"
        os.replace(temporary, target)
        with Session(engine) as session:
            user = session.exec(select(User).where(User.id == user_id).with_for_update()).first()
            if user and user.status == "active" and not user.avatar_edited:
                user.avatar_path = f"/media/avatars/{user_id}/telegram.{extension}"
                user.updated_at = utc_now()
                session.add(user)
                session.commit()
    except Exception:
        logging.warning("Telegram avatar refresh failed")


def _message(chat_id: int, text_value: str, settings: Settings, buttons: list[list[dict]] | None = None) -> None:
    payload = {"chat_id": chat_id, "text": text_value}
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}
    _telegram("sendMessage", payload, settings)


def _session_for_token(session: Session, token: str, settings: Settings, *, touch: bool = True) -> tuple[LoginSession, User] | None:
    if not token:
        return None
    login = session.exec(select(LoginSession).where(LoginSession.token_hash == _digest(token))).first()
    if not login:
        return None
    now = utc_now()
    user = session.get(User, login.user_id)
    if (login.revoked_at or _utc(login.expires_at) <= now or
            _utc(login.last_seen_at) + timedelta(days=settings.auth_idle_days) <= now or
            not user or user.status != "active"):
        return None
    if touch and _utc(login.last_seen_at) + timedelta(minutes=5) < now:
        login.last_seen_at = now
        session.add(login)
        session.commit()
    return login, user


def require_user_id(request: Request) -> int:
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        raise HTTPException(401, "Требуется вход")
    return user_id


def _valid_csrf(token: str, settings: Settings) -> bool:
    nonce, separator, signature = token.partition(".")
    return bool(nonce and separator and hmac.compare_digest(signature, _mac(settings, "csrf:" + nonce)))


def issue_csrf(response: Response, settings: Settings) -> str:
    nonce = secrets.token_urlsafe(32)
    token = f"{nonce}.{_mac(settings, 'csrf:' + nonce)}"
    response.set_cookie(CSRF_COOKIE, token, httponly=True, secure=True, samesite="lax", path="/")
    return token


def validate_csrf(request: Request, settings: Settings) -> None:
    if request.headers.get("origin") != settings.public_origin.rstrip("/"):
        raise HTTPException(403, "Недопустимый источник запроса")
    cookie = request.cookies.get(CSRF_COOKIE, "")
    header = request.headers.get("x-csrf-token", "")
    if not hmac.compare_digest(cookie, header) or not _valid_csrf(cookie, settings):
        raise HTTPException(403, "Обновите страницу и повторите действие")


@router.get("/csrf")
def csrf(request: Request, response: Response, settings: Settings = Depends(get_settings)) -> dict:
    _configured(settings)
    # Tabs share cookies. Rotating on every bootstrap breaks mutations in older tabs.
    token = request.cookies.get(CSRF_COOKIE, "")
    from .yandex_auth import configured as yandex_configured
    return {"csrf_token": token if _valid_csrf(token, settings) else issue_csrf(response, settings),
            "providers": {"telegram": True, "yandex": yandex_configured(settings)}}


@router.post("/telegram/start")
def start_telegram(
    payload: ChallengeRequest, response: Response, request: Request,
    session: Session = Depends(get_session), settings: Settings = Depends(get_settings),
) -> dict:
    _configured(settings)
    _rate_limit(session, settings, "start-browser:" + request.cookies.get(CSRF_COOKIE, ""), 5, 600)
    _rate_limit(session, settings, "start-ip:" + _ip_hash(request, settings), 80, 600)
    _rate_limit(session, settings, "start-global", 1000, 86400)
    challenge_id = secrets.token_urlsafe(32)
    browser_secret = secrets.token_urlsafe(32)
    code = f"{secrets.randbelow(1_000_000):06d}"
    challenge = AuthChallenge(
        id=challenge_id, browser_secret_hash=_digest(browser_secret),
        code_mac=_mac(settings, f"code:{challenge_id}:{code}"),
        return_path=_safe_return(payload.return_to), ip_hash=_ip_hash(request, settings),
        expires_at=utc_now() + timedelta(minutes=settings.auth_challenge_minutes),
    )
    session.add(challenge)
    session.commit()
    response.set_cookie(
        CHALLENGE_COOKIE, f"{challenge_id}.{browser_secret}", httponly=True,
        secure=True, samesite="lax", path="/", max_age=settings.auth_challenge_minutes * 60,
    )
    return {
        "challenge_id": challenge_id, "code": code,
        "bot_url": f"https://t.me/{settings.telegram_bot_username}?start={challenge_id}",
        "expires_at": challenge.expires_at,
    }


@router.get("/telegram/status")
def challenge_status(
    challenge_id: str, request: Request, session: Session = Depends(get_session),
) -> dict:
    challenge = session.get(AuthChallenge, challenge_id)
    if not challenge:
        raise HTTPException(404, "Запрос входа не найден")
    _browser_challenge(request, challenge)
    state = "expired" if _utc(challenge.expires_at) <= utc_now() else challenge.state
    return {"state": state, "expires_at": challenge.expires_at}


@router.post("/telegram/finish")
def finish_telegram(
    payload: ChallengeFinish, response: Response, request: Request, tasks: BackgroundTasks,
    session: Session = Depends(get_session), settings: Settings = Depends(get_settings),
) -> dict:
    _configured(settings)
    challenge = session.exec(select(AuthChallenge).where(AuthChallenge.id == payload.challenge_id).with_for_update()).first()
    if not challenge:
        raise HTTPException(404, "Запрос входа не найден")
    _browser_challenge(request, challenge)
    if _utc(challenge.expires_at) <= utc_now() or challenge.state != "approved" or challenge.consumed_at:
        raise HTTPException(409, "Вход не подтверждён или срок запроса истёк")
    telegram_id = challenge.telegram_user_id
    if not telegram_id:
        raise HTTPException(409, "Telegram не подтвердил вход")
    # Serialize first registration across distinct approved challenges for one Telegram ID.
    if session.bind.dialect.name == "postgresql":
        session.exec(text("SELECT pg_advisory_xact_lock(:key)").bindparams(key=telegram_id)).one()
    identity = session.exec(select(AuthIdentity).where(
        AuthIdentity.provider == "telegram", AuthIdentity.provider_subject == str(telegram_id),
    )).first()
    now = utc_now()
    if identity:
        user = session.exec(select(User).where(User.id == identity.user_id).with_for_update()).first()
        if not user or user.status != "active":
            raise HTTPException(403, "Аккаунт недоступен")
        identity.verified_attributes = challenge.telegram_profile
        identity.updated_at = now
        session.add(identity)
    else:
        profile = challenge.telegram_profile
        name = " ".join(part for part in (profile.get("first_name"), profile.get("last_name")) if part).strip()
        user = User(display_name=name or "Пользователь Telegram")
        session.add(user)
        session.flush()
        session.add(AuthIdentity(
            user_id=user.id, provider="telegram", provider_subject=str(telegram_id),
            verified_attributes=profile,
        ))
    if not user.name_edited:
        profile = challenge.telegram_profile
        name = " ".join(part for part in (profile.get("first_name"), profile.get("last_name")) if part).strip()
        if name:
            user.display_name = name
    user.last_login_at = now
    user.updated_at = now
    previous = _session_for_token(session, request.cookies.get(SESSION_COOKIE, ""), settings, touch=False)
    if previous:
        previous[0].revoked_at = now
        session.add(previous[0])
    token = secrets.token_urlsafe(48)
    session.add(LoginSession(
        user_id=user.id, token_hash=_digest(token), expires_at=now + timedelta(days=settings.auth_session_days),
        user_agent=request.headers.get("user-agent", "")[:255], ip_hash=_ip_hash(request, settings),
    ))
    challenge.state = "consumed"
    challenge.consumed_at = now
    session.add_all([user, challenge])
    session.commit()
    response.set_cookie(
        SESSION_COOKIE, token, httponly=True, secure=True, samesite="lax", path="/",
        max_age=settings.auth_session_days * 86400,
    )
    response.delete_cookie(CHALLENGE_COOKIE, path="/", secure=True, samesite="lax")
    tasks.add_task(_refresh_avatar, user.id, telegram_id, settings)
    return {"return_to": challenge.return_path}


@router.get("/me")
def me(request: Request, session: Session = Depends(get_session)) -> dict:
    current = _session_for_token(session, request.cookies.get(SESSION_COOKIE, ""), get_settings())
    if not current:
        raise HTTPException(401, "Требуется вход")
    login, user = current
    identities = session.exec(select(AuthIdentity).where(AuthIdentity.user_id == user.id)).all()
    telegram = next((identity for identity in identities if identity.provider == "telegram"), None)
    email = next((identity for identity in identities if identity.provider == "email"), None)
    return {
        "id": user.id, "display_name": user.display_name, "avatar_path": user.avatar_path,
        "providers": [identity.provider for identity in identities], "session_id": login.id,
        "telegram_username": telegram.verified_attributes.get("username") if telegram else None,
        "email": email.provider_subject if email else None,
    }


@router.patch("/profile")
def update_profile(payload: ProfileUpdate, request: Request, session: Session = Depends(get_session)) -> dict:
    user = session.exec(select(User).where(User.id == require_user_id(request)).with_for_update()).one()
    user.display_name = payload.display_name
    user.name_edited = True
    user.updated_at = utc_now()
    session.add(user)
    session.commit()
    return {"display_name": user.display_name}


def _profile_photo(content: bytes) -> bytes:
    """Decode, resize and re-encode: never serve uploaded markup or metadata."""
    try:
        with Image.open(io.BytesIO(content), formats=["JPEG", "PNG"]) as photo:
            if photo.width * photo.height > 16_000_000:
                raise HTTPException(422, "Фото слишком большое. Максимум 16 мегапикселей")
            photo.load()
            photo = ImageOps.exif_transpose(photo)
            photo = ImageOps.fit(photo.convert("RGB"), (512, 512), method=Image.Resampling.LANCZOS)
            output = io.BytesIO()
            photo.save(output, format="JPEG", quality=88)
            return output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise HTTPException(422, "Не удалось прочитать фото. Выберите JPG или PNG")


def _store_photo(content: bytes, user_id: int, settings: Settings) -> str:
    content = _profile_photo(content)
    destination = settings.media_root / "avatars" / str(user_id)
    destination.mkdir(parents=True, exist_ok=True)
    filename = f"custom-{secrets.token_hex(12)}.jpg"
    (destination / filename).write_bytes(content)
    return f"/media/avatars/{user_id}/{filename}"


def _remove_custom_photo(path: str | None, user_id: int, settings: Settings) -> None:
    if path and re.fullmatch(rf"/media/avatars/{user_id}/custom-[a-f0-9]{{24}}\.jpg", path):
        try:
            (settings.media_root / path.removeprefix("/media/")).unlink(missing_ok=True)
        except OSError:
            logging.warning("Old profile photo cleanup deferred")


@router.put("/profile/avatar")
async def upload_avatar(request: Request, session: Session = Depends(get_session), settings: Settings = Depends(get_settings)) -> dict:
    user_id = require_user_id(request)
    _rate_limit(session, settings, f"profile-photo:{user_id}", 20, 3600)
    if request.headers.get("content-type", "").split(";", 1)[0] not in {"image/jpeg", "image/png"}:
        raise HTTPException(415, "Выберите фото в формате JPG или PNG")
    length = request.headers.get("content-length", "0")
    if not length.isdecimal() or int(length) > 2 * 1024 * 1024:
        raise HTTPException(413, "Размер фото не должен превышать 2 МБ")
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > 2 * 1024 * 1024:
            raise HTTPException(413, "Размер фото не должен превышать 2 МБ")
    path = await run_in_threadpool(_store_photo, bytes(content), user_id, settings)
    try:
        user = session.exec(select(User).where(User.id == user_id).with_for_update()).one()
        previous = user.avatar_path
        user.avatar_path, user.avatar_edited, user.updated_at = path, True, utc_now()
        session.add(user)
        session.commit()
    except Exception:
        _remove_custom_photo(path, user_id, settings)
        raise
    _remove_custom_photo(previous, user_id, settings)
    return {"avatar_path": path}


@router.delete("/profile/avatar")
def remove_avatar(request: Request, session: Session = Depends(get_session), settings: Settings = Depends(get_settings)) -> dict:
    user_id = require_user_id(request)
    user = session.exec(select(User).where(User.id == user_id).with_for_update()).one()
    previous = user.avatar_path
    user.avatar_path, user.avatar_edited, user.updated_at = None, True, utc_now()
    session.add(user)
    session.commit()
    _remove_custom_photo(previous, user_id, settings)
    return {"avatar_path": None}


@router.get("/sessions")
def list_sessions(request: Request, session: Session = Depends(get_session)) -> list[dict]:
    user_id = require_user_id(request)
    settings = get_settings()
    current = _session_for_token(session, request.cookies.get(SESSION_COOKIE, ""), settings)
    rows = session.exec(select(LoginSession).where(LoginSession.user_id == user_id).order_by(LoginSession.created_at.desc())).all()
    return [{"id": row.id, "created_at": row.created_at, "last_seen_at": row.last_seen_at,
             "user_agent": row.user_agent, "current": bool(current and current[0].id == row.id)}
            for row in rows if not row.revoked_at and _utc(row.expires_at) > utc_now()
            and _utc(row.last_seen_at) + timedelta(days=settings.auth_idle_days) > utc_now()]


@router.post("/logout")
def logout(response: Response, request: Request, session: Session = Depends(get_session)) -> dict:
    current = _session_for_token(session, request.cookies.get(SESSION_COOKIE, ""), get_settings())
    if current:
        current[0].revoked_at = utc_now()
        session.add(current[0])
        session.commit()
    response.delete_cookie(SESSION_COOKIE, path="/", secure=True, samesite="lax")
    return {"ok": True}


@router.post("/logout-all")
def logout_all(response: Response, request: Request, session: Session = Depends(get_session)) -> dict:
    user_id = require_user_id(request)
    for login in session.exec(select(LoginSession).where(LoginSession.user_id == user_id, LoginSession.revoked_at == None)).all():
        login.revoked_at = utc_now()
        session.add(login)
    session.commit()
    response.delete_cookie(SESSION_COOKIE, path="/", secure=True, samesite="lax")
    return {"ok": True}


@router.post("/sessions/{session_id}/revoke")
def revoke_session(session_id: int, request: Request, response: Response, session: Session = Depends(get_session)) -> dict:
    user_id = require_user_id(request)
    login = session.get(LoginSession, session_id)
    if not login or login.user_id != user_id:
        raise HTTPException(404, "Сессия не найдена")
    login.revoked_at = utc_now()
    session.add(login)
    session.commit()
    if hmac.compare_digest(login.token_hash, _digest(request.cookies.get(SESSION_COOKIE, ""))):
        response.delete_cookie(SESSION_COOKIE, path="/", secure=True, samesite="lax")
    return {"ok": True}


def _handle_telegram_update(update: dict, session: Session, settings: Settings, tasks: BackgroundTasks) -> None:
    update_id = update.get("update_id")
    if not isinstance(update_id, int):
        return
    inserted = session.exec(text("""
        INSERT INTO telegram_updates (update_id, created_at) VALUES (:id, :now)
        ON CONFLICT (update_id) DO NOTHING RETURNING update_id
    """).bindparams(id=update_id, now=utc_now())).first()
    if not inserted:
        return
    message = update.get("message")
    callback = update.get("callback_query")
    if isinstance(message, dict):
        sender, chat = message.get("from") or {}, message.get("chat") or {}
        telegram_id = sender.get("id")
        if not isinstance(telegram_id, int) or sender.get("is_bot") or chat.get("type") != "private" or chat.get("id") != telegram_id:
            return
        _rate_limit(session, settings, f"bot-message:{telegram_id}", 30, 600)
        body = (message.get("text") or "").strip()
        if body.startswith("/start"):
            parts = body.split()
            challenge_id = parts[1] if len(parts) == 2 else ""
            challenge = session.exec(select(AuthChallenge).where(AuthChallenge.id == challenge_id).with_for_update()).first() if CHALLENGE_RE.fullmatch(challenge_id) else None
            if not challenge or _utc(challenge.expires_at) <= utc_now() or challenge.state not in {"pending", "awaiting_code"}:
                tasks.add_task(_message, telegram_id, f"Откройте {settings.public_origin}/login и начните вход заново.", settings)
                return
            if challenge.telegram_user_id not in {None, telegram_id}:
                return
            challenge.telegram_user_id = telegram_id
            challenge.state = "awaiting_code"
            challenge.telegram_profile = {key: sender[key] for key in ("first_name", "last_name", "username") if isinstance(sender.get(key), str)}
            session.add(challenge)
            requested = challenge.created_at.strftime("%d.%m.%Y %H:%M UTC")
            tasks.add_task(_message, telegram_id,
                f"Вход на {settings.public_origin}, запрос от {requested}.\n"
                "Введите короткий код, показанный в браузере. Подтверждайте только вход, который начали сами.", settings)
            return
        challenge = session.exec(select(AuthChallenge).where(
            AuthChallenge.telegram_user_id == telegram_id, AuthChallenge.state == "awaiting_code",
        ).order_by(AuthChallenge.created_at.desc()).with_for_update()).first()
        if not challenge or _utc(challenge.expires_at) <= utc_now():
            return
        _rate_limit(session, settings, f"bot-code:{telegram_id}", 12, 600)
        challenge.attempts += 1
        if challenge.attempts > 5 or not hmac.compare_digest(challenge.code_mac, _mac(settings, f"code:{challenge.id}:{body}")):
            if challenge.attempts >= 5:
                challenge.state = "denied"
            session.add(challenge)
            tasks.add_task(_message, telegram_id, "Неверный код или лимит попыток исчерпан.", settings)
            return
        challenge.state = "code_verified"
        session.add(challenge)
        tasks.add_task(_message, telegram_id,
            f"Подтвердить вход на {settings.public_origin}?",
            settings, [[{"text": "Подтвердить вход", "callback_data": "yes:" + challenge.id},
                        {"text": "Отклонить", "callback_data": "no:" + challenge.id}]])
        return
    if isinstance(callback, dict):
        sender = callback.get("from") or {}
        chat = (callback.get("message") or {}).get("chat") or {}
        telegram_id = sender.get("id")
        if not isinstance(telegram_id, int) or sender.get("is_bot") or chat.get("type") != "private" or chat.get("id") != telegram_id:
            return
        _rate_limit(session, settings, f"bot-callback:{telegram_id}", 30, 600)
        decision, separator, challenge_id = (callback.get("data") or "").partition(":")
        if not separator or decision not in {"yes", "no"} or not CHALLENGE_RE.fullmatch(challenge_id):
            return
        challenge = session.exec(select(AuthChallenge).where(AuthChallenge.id == challenge_id).with_for_update()).first()
        if not challenge or challenge.telegram_user_id != telegram_id or challenge.state != "code_verified" or _utc(challenge.expires_at) <= utc_now():
            return
        challenge.state = "approved" if decision == "yes" else "denied"
        challenge.approved_at = utc_now() if decision == "yes" else None
        session.add(challenge)
        tasks.add_task(_telegram, "answerCallbackQuery", {"callback_query_id": callback.get("id"),
            "text": "Вход подтверждён. Вернитесь в исходный браузер." if decision == "yes" else "Вход отклонён."}, settings)


def _process_polled_update(update: dict, settings: Settings) -> None:
    """Commit the update before acknowledging its offset to Telegram."""
    tasks = BackgroundTasks()
    with Session(engine) as session:
        try:
            _handle_telegram_update(update, session, settings, tasks)
        except HTTPException as error:
            if error.status_code != 429:
                raise
            # A rate-limited Telegram update must not block the whole offset.
        session.commit()
    asyncio.run(tasks())


def _poll_telegram(settings: Settings, stop: threading.Event) -> None:
    # A session-level PostgreSQL lock gives one poller per database, even with
    # several API containers. The lock connection stays checked out throughout.
    lock_key = 0x48595045504F4C4C
    while not stop.is_set():
        try:
            with engine.connect() as leader:
                acquired = leader.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_key}).scalar()
                leader.commit()
                if not acquired:
                    stop.wait(5)
                    continue
                try:
                    if _telegram_result("deleteWebhook", {"drop_pending_updates": False}, settings) is not True:
                        logging.warning("Telegram polling could not disable webhook; retrying")
                        stop.wait(5)
                        continue
                    logging.info("Telegram polling active")
                    offset = None
                    while not stop.is_set():
                        leader.execute(text("SELECT 1"))
                        leader.commit()
                        payload = {"timeout": 15, "limit": 25, "allowed_updates": ["message", "callback_query"]}
                        if offset is not None:
                            payload["offset"] = offset
                        updates = _telegram_result("getUpdates", payload, settings, timeout=22)
                        if not isinstance(updates, list):
                            stop.wait(5)
                            continue
                        for update in updates:
                            if stop.is_set():
                                break
                            if not isinstance(update, dict) or not isinstance(update.get("update_id"), int):
                                continue
                            try:
                                _process_polled_update(update, settings)
                            except Exception:
                                # No exception text: Bot API URLs and user data can be sensitive.
                                logging.warning("Telegram update processing failed; will retry")
                                stop.wait(5)
                                break
                            offset = update["update_id"] + 1
                finally:
                    leader.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_key})
                    leader.commit()
        except Exception:
            logging.warning("Telegram polling unavailable; retrying")
        stop.wait(5)


def start_telegram_polling(settings: Settings) -> tuple[threading.Event, threading.Thread] | None:
    if settings.telegram_delivery_mode != "polling":
        return None
    _configured(settings)
    stop = threading.Event()
    thread = threading.Thread(target=_poll_telegram, args=(settings, stop), name="telegram-poll", daemon=True)
    thread.start()
    return stop, thread


@webhook_router.post("/webhook", include_in_schema=False)
async def telegram_webhook(
    request: Request, tasks: BackgroundTasks,
    session: Session = Depends(get_session), settings: Settings = Depends(get_settings),
) -> dict:
    secret = request.headers.get("x-telegram-bot-api-secret-token", "")
    if not settings.telegram_webhook_secret or not hmac.compare_digest(secret, settings.telegram_webhook_secret):
        raise HTTPException(403, "Недопустимый webhook")
    length = request.headers.get("content-length", "0")
    if not length.isdecimal():
        raise HTTPException(400, "Неверный размер запроса")
    if int(length) > 65536:
        raise HTTPException(413, "Слишком большой запрос")
    body = await request.body()
    if len(body) > 65536:
        raise HTTPException(413, "Слишком большой запрос")
    try:
        update = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(400, "Неверный формат запроса")
    if not isinstance(update, dict):
        raise HTTPException(400, "Неверный формат запроса")
    _configured(settings)
    _handle_telegram_update(update, session, settings, tasks)
    session.commit()
    return {"ok": True}
