"""Email OTP login, including verified ownership of a unique Yandex profile email."""
import hashlib
import hmac
import json
import re
import secrets
from datetime import timedelta
from urllib.request import HTTPRedirectHandler, Request as UrlRequest, build_opener

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, text
from sqlmodel import Session, select

from .auth import SESSION_COOKIE, CSRF_COOKIE, _digest, _ip_hash, _mac, _rate_limit, _safe_return, _session_for_token, _utc
from .config import Settings, get_settings
from .database import get_session
from .models import AuthIdentity, EmailChallenge, LoginSession, User, utc_now

router = APIRouter(prefix="/api/auth/email")
COOKIE = "__Host-hype_email"
DOMAINS = frozenset("yandex.ru ya.ru mail.ru bk.ru inbox.ru list.ru internet.ru rambler.ru lenta.ru autorambler.ru myrambler.ru ro.ru r0.ru".split())


class StartRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    return_to: str = Field(default="/today", max_length=512)


class FinishRequest(BaseModel):
    challenge_id: str = Field(min_length=43, max_length=43)
    code: str = Field(pattern=r"^[0-9]{6}$")


def configured(settings):
    return bool(settings.unisender_go_api_key and settings.email_from_address
                and settings.public_origin.startswith("https://") and len(settings.auth_code_secret) >= 32)


def normalize_email(value):
    value = value.strip().lower()
    local, _, domain = value.rpartition("@")
    if domain not in DOMAINS:
        raise HTTPException(422, "Вход с этой почтой недоступен. Hype Hunter поддерживает вход по коду только с адресов российских почтовых сервисов из разрешённого списка. Используйте почту Яндекса, Mail.ru или Рамблера либо войдите через Яндекс ID или Telegram. Пароль создавать не нужно.")
    if (not re.fullmatch(r"[a-z0-9][a-z0-9._+\-]{0,63}", local)
            or local.endswith(".") or ".." in local):
        raise HTTPException(422, "Укажите адрес Яндекс, Mail.ru или Рамблер из поддерживаемых почтовых сервисов")
    return value


def lock_email(session, email):
    if session.bind.dialect.name == "postgresql":
        key = int.from_bytes(hashlib.sha256(("email:" + email.strip().lower()).encode()).digest()[:8], "big", signed=True)
        session.exec(text("SELECT pg_advisory_xact_lock(:key)").bindparams(key=key)).one()


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def send_code(settings, email, code, challenge_id):
    # No tracking, credentials in headers only. Never log request/response bodies.
    body = {"message": {
        "recipients": [{"email": email}], "from_email": settings.email_from_address,
        "from_name": settings.email_from_name, "subject": "Код входа в Hype Hunter",
        "body": {"plaintext": f"Ваш код входа в Hype Hunter: {code}\n\n"
                 f"Введите его в браузере, где начали вход на {settings.public_origin}. "
                 f"Код действует {settings.email_code_minutes} минут. Никому его не сообщайте.\n"
                 "Если вы не запрашивали вход, просто проигнорируйте это письмо."},
        "track_read": 0, "track_links": 0, "template_engine": "none",
        "idempotence_key": challenge_id,
    }}
    request = UrlRequest("https://goapi.unisender.ru/ru/transactional/api/v1/email/send.json",
                         data=json.dumps(body).encode(), headers={"Content-Type": "application/json",
                         "X-API-KEY": settings.unisender_go_api_key})
    with build_opener(NoRedirect()).open(request, timeout=12) as response:
        raw = response.read(65537)
    if len(raw) > 65536:
        raise ValueError("Mail response too large")
    result = json.loads(raw)
    if not isinstance(result, dict) or result.get("status") != "success" or result.get("failed_emails"):
        raise ValueError("Mail not accepted")


def require_guest(request, session, settings):
    if not configured(settings):
        raise HTTPException(503, "Вход по почте пока недоступен")
    if _session_for_token(session, request.cookies.get(SESSION_COOKIE, ""), settings, touch=False):
        raise HTTPException(409, "Сначала выйдите из текущего аккаунта. Вход по почте не привязывает адрес к нему")


@router.post("/start")
def start(payload: StartRequest, request: Request, response: Response,
          session: Session = Depends(get_session), settings: Settings = Depends(get_settings)):
    require_guest(request, session, settings)
    email = normalize_email(payload.email)
    # Counters use independent atomic PostgreSQL transactions across API replicas.
    for key, limit, period in (
        ("email-browser:" + request.cookies.get(CSRF_COOKIE, ""), 10, 3600),
        ("email-ip:" + _ip_hash(request, settings), 50, 3600),
        ("email-address-hour:" + email, 6, 3600),
        ("email-address-cooldown:" + email, 1, settings.email_resend_seconds),
        ("email-global", settings.email_hourly_limit, 3600),
    ):
        _rate_limit(session, settings, key, limit, period)
    secret = secrets.token_urlsafe(32)
    code = f"{secrets.randbelow(1000000):06d}"
    challenge_id = secrets.token_urlsafe(32)
    pending = EmailChallenge(id=challenge_id, email=email, browser_secret_hash=_digest(secret),
        code_mac=_mac(settings, f"email-login:{challenge_id}:{code}"),
        return_path=_safe_return(payload.return_to),
        expires_at=utc_now() + timedelta(minutes=settings.email_code_minutes))
    session.add(pending)
    session.commit()
    try:
        send_code(settings, email, code, challenge_id)
    except Exception:
        pending.state = "failed"
        session.add(pending)
        session.commit()
        raise HTTPException(503, "Не удалось отправить письмо. Повторите попытку через минуту") from None
    pending.state = "pending"
    session.add(pending)
    session.commit()
    response.set_cookie(COOKIE, challenge_id + "." + secret,
                        max_age=settings.email_code_minutes * 60, secure=True, httponly=True, samesite="lax", path="/")
    return {"challenge_id": challenge_id, "expires_at": pending.expires_at,
            "expires_in_minutes": settings.email_code_minutes, "resend_after": settings.email_resend_seconds}


@router.post("/finish")
def finish(payload: FinishRequest, request: Request, response: Response,
           session: Session = Depends(get_session), settings: Settings = Depends(get_settings)):
    require_guest(request, session, settings)
    _rate_limit(session, settings, "email-verify:" + _ip_hash(request, settings), 120, 600)
    pending = session.exec(select(EmailChallenge).where(EmailChallenge.id == payload.challenge_id).with_for_update()).first()
    cookie_id, _, secret = request.cookies.get(COOKIE, "").partition(".")
    if (not pending or cookie_id != payload.challenge_id or not secret
            or not hmac.compare_digest(pending.browser_secret_hash, _digest(secret))):
        raise HTTPException(403, "Начните вход заново в этом браузере")
    if (pending.state != "pending" or pending.attempts >= settings.email_code_attempts
            or _utc(pending.expires_at) <= utc_now()):
        raise HTTPException(410, "Код больше не действует. Запросите новый")
    pending.attempts += 1
    if not hmac.compare_digest(pending.code_mac, _mac(settings, f"email-login:{pending.id}:{payload.code}")):
        if pending.attempts >= settings.email_code_attempts:
            pending.state = "locked"
        session.add(pending)
        session.commit()
        raise HTTPException(400, "Неверный код. Проверьте письмо" if pending.state != "locked" else "Попытки закончились. Запросите новый код")
    # Serialize registration of the same address, including different browsers.
    lock_email(session, pending.email)
    identity = session.exec(select(AuthIdentity).where(AuthIdentity.provider == "email", AuthIdentity.provider_subject == pending.email)).first()
    # Only AFTER code verification: the owner explicitly requested this matching rule.
    # Never merge two existing users or trust an email posted by the browser.
    yandex_ids = session.exec(select(AuthIdentity.user_id).where(AuthIdentity.provider == "yandex",
        func.lower(func.trim(AuthIdentity.verified_attributes["default_email"].as_string())) == pending.email)).all()
    candidates = set(yandex_ids)
    if identity:
        candidates.add(identity.user_id)
    if len(candidates) > 1:
        pending.state = "locked"
        session.add(pending)
        session.commit()
        raise HTTPException(409, "Этот адрес связан с несколькими аккаунтами. Войдите через Яндекс или Telegram")
    if candidates:
        user = session.get(User, next(iter(candidates)))
    else:
        user = User(display_name=pending.email.split("@")[0])
        session.add(user)
        session.flush()
    if not user or user.status != "active":
        raise HTTPException(403, "Аккаунт недоступен. Обратитесь в поддержку")
    if not identity:
        session.add(AuthIdentity(user_id=user.id, provider="email", provider_subject=pending.email,
                                 verified_attributes={"email": pending.email}))
    now = utc_now()
    user.last_login_at = now
    user.updated_at = now
    session.add(user)
    token = secrets.token_urlsafe(48)
    session.add(LoginSession(user_id=user.id, token_hash=_digest(token),
        expires_at=now + timedelta(days=settings.auth_session_days),
        user_agent=request.headers.get("user-agent", "")[:255], ip_hash=_ip_hash(request, settings)))
    pending.state = "consumed"
    pending.consumed_at = now
    session.add(pending)
    session.commit()
    response.set_cookie(SESSION_COOKIE, token, max_age=settings.auth_session_days * 86400,
                        secure=True, httponly=True, samesite="lax", path="/")
    response.delete_cookie(COOKIE, secure=True, httponly=True, samesite="lax", path="/")
    return {"return_to": pending.return_path}
