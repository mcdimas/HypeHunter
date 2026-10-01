"""Yandex Authorization Code + S256 PKCE; credentials never reach the frontend."""
import base64
import hashlib
import hmac
import json
import re
import secrets
from datetime import timedelta
from typing import Literal
from urllib.parse import urlencode
from urllib.request import Request as UrlRequest, urlopen

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlmodel import Session, select

from .auth import SESSION_COOKIE, _digest, _ip_hash, _mac, _rate_limit, _safe_return, _session_for_token, _utc
from .config import Settings, get_settings
from .database import get_session
from .models import AuthIdentity, LoginSession, OAuthRequest, User, utc_now

router = APIRouter(prefix="/api/auth/yandex")
COOKIE = "__Host-hype_yandex"


class StartRequest(BaseModel):
    return_to: str = Field(default="/today", max_length=512)
    purpose: Literal["login", "link"] = "login"


def configured(settings):
    return bool(settings.yandex_client_id and settings.public_origin.startswith("https://")
                and len(settings.auth_code_secret) >= 32)


def _verifier(settings, request_id, browser_secret):
    return _mac(settings, f"yandex-pkce:{request_id}:{browser_secret}")


def _callback_url(settings):
    return settings.public_origin.rstrip("/") + "/api/auth/yandex/callback"


def _json(request):
    with urlopen(request, timeout=10) as response:
        raw = response.read(65537)
    if len(raw) > 65536:
        raise ValueError("Provider response too large")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Invalid provider response")
    return value


def _profile(code, verifier, settings):
    # Yandex explicitly permits PKCE code_verifier without a client_secret.
    token = _json(UrlRequest("https://oauth.yandex.ru/token", data=urlencode({
        "grant_type": "authorization_code", "code": code,
        "client_id": settings.yandex_client_id, "code_verifier": verifier,
    }).encode(), headers={"Content-Type": "application/x-www-form-urlencoded"}))
    access = token.get("access_token")
    if not isinstance(access, str) or not access or len(access) > 8192:
        raise ValueError("No access token")
    profile = _json(UrlRequest("https://login.yandex.ru/info?format=json",
                              headers={"Authorization": "OAuth " + access}))
    subject = profile.get("id")
    if not isinstance(subject, str) or not subject.isascii() or not subject.isdigit() or len(subject) > 255:
        raise ValueError("No stable Yandex ID")
    if profile.get("client_id") != settings.yandex_client_id:
        raise ValueError("Unexpected OAuth client")
    # Email is a profile attribute, never a key for merging accounts or email login.
    result = {key: str(profile.get(key) or "")[:255] for key in ("id", "display_name", "first_name", "last_name", "login")}
    email = profile.get("default_email")
    if isinstance(email, str) and len(email) <= 254 and re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        result["default_email"] = email
    return result


def _redirect(path):
    response = RedirectResponse(path, status_code=303, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})
    response.delete_cookie(COOKIE, path="/", secure=True, httponly=True, samesite="lax")
    return response


@router.post("/start")
def start(payload: StartRequest, request: Request, response: Response,
          session: Session = Depends(get_session), settings: Settings = Depends(get_settings)):
    if not configured(settings):
        raise HTTPException(503, "Вход через Яндекс ещё не настроен")
    _rate_limit(session, settings, "yandex-start:" + _ip_hash(request, settings), 80, 600)
    _rate_limit(session, settings, "yandex-browser:" + request.cookies.get("__Host-hype_csrf", ""), 10, 600)
    current = _session_for_token(session, request.cookies.get(SESSION_COOKIE, ""), settings, touch=False)
    link_session_id = None
    if payload.purpose == "link":
        if not current:
            raise HTTPException(401, "Войдите в аккаунт перед подключением Яндекса")
        if _utc(current[0].created_at) < utc_now() - timedelta(minutes=5):
            raise HTTPException(428, "Для подключения Яндекса выйдите и снова войдите текущим способом, затем вернитесь сюда в течение пяти минут")
        link_session_id = current[0].id
    elif current:
        raise HTTPException(409, "Подключите Яндекс в разделе «Вход и безопасность» вашего профиля")
    secret = secrets.token_urlsafe(32)
    pending = OAuthRequest(id=secrets.token_urlsafe(32), browser_secret_hash=_digest(secret),
        purpose=payload.purpose, link_session_id=link_session_id,
        return_path="/account?tab=security" if link_session_id else _safe_return(payload.return_to),
        expires_at=utc_now() + timedelta(minutes=5))
    session.add(pending)
    session.commit()
    verifier = _verifier(settings, pending.id, secret)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    response.set_cookie(COOKIE, pending.id + "." + secret, max_age=300,
                        secure=True, httponly=True, samesite="lax", path="/")
    return {"authorize_url": "https://oauth.yandex.ru/authorize?" + urlencode({
        "response_type": "code", "client_id": settings.yandex_client_id,
        "redirect_uri": _callback_url(settings), "scope": "login:info login:email", "force_confirm": "yes",
        "state": pending.id, "code_challenge": challenge, "code_challenge_method": "S256"})}


@router.get("/callback")
def callback(request: Request, session: Session = Depends(get_session), settings: Settings = Depends(get_settings)):
    params = request.query_params
    state = params.get("state", "")
    if not configured(settings) or len(state) != 43 or any(len(params.getlist(k)) > 1 for k in ("state", "code", "error")):
        return _redirect("/login?auth_error=yandex_invalid")
    pending = session.exec(select(OAuthRequest).where(OAuthRequest.id == state).with_for_update()).first()
    cookie_id, _, secret = request.cookies.get(COOKIE, "").partition(".")
    if (not pending or cookie_id != state or not secret or
            not hmac.compare_digest(pending.browser_secret_hash, _digest(secret))):
        return _redirect("/login?auth_error=yandex_invalid")
    destination = "/account?tab=security&" if pending.purpose == "link" else "/login?"
    if pending.state != "pending" or _utc(pending.expires_at) <= utc_now():
        return _redirect(destination + "auth_error=yandex_expired")
    # Claim before contacting the provider: parallel callbacks cannot exchange twice.
    pending.state = "consumed"
    pending.consumed_at = utc_now()
    session.add(pending)
    session.commit()
    if params.get("error"):
        return _redirect(destination + "auth_error=yandex_denied")
    code = params.get("code", "")
    if not code or len(code) > 2048:
        return _redirect(destination + "auth_error=yandex_invalid")
    try:
        profile = _profile(code, _verifier(settings, state, secret), settings)
    except Exception:
        # Provider exceptions may include tokens or code. Never log their content.
        return _redirect(destination + "auth_error=yandex_unavailable")
    subject = profile["id"]
    if session.bind.dialect.name == "postgresql":
        key = int.from_bytes(hashlib.sha256(("yandex:" + subject).encode()).digest()[:8], "big", signed=True)
        session.exec(text("SELECT pg_advisory_xact_lock(:key)").bindparams(key=key)).one()
    identity = session.exec(select(AuthIdentity).where(AuthIdentity.provider == "yandex", AuthIdentity.provider_subject == subject)).first()
    current = _session_for_token(session, request.cookies.get(SESSION_COOKIE, ""), settings, touch=False)
    if pending.purpose == "link":
        if not current or current[0].id != pending.link_session_id:
            return _redirect("/login?auth_error=yandex_invalid")
        user = session.exec(select(User).where(User.id == current[1].id).with_for_update()).one()
        if identity and identity.user_id != user.id:
            return _redirect(destination + "auth_error=yandex_conflict")
        other = session.exec(select(AuthIdentity).where(AuthIdentity.user_id == user.id, AuthIdentity.provider == "yandex")).first()
        if other and other.provider_subject != subject:
            return _redirect(destination + "auth_error=yandex_conflict")
    elif current:
        return _redirect("/account?tab=security&auth_error=yandex_invalid")
    elif identity:
        user = session.get(User, identity.user_id)
    else:
        user = User(display_name=profile["display_name"] or profile["first_name"] or "Пользователь Яндекса")
        session.add(user)
        session.flush()
    if not user or user.status != "active":
        return _redirect(destination + "auth_error=yandex_disabled")
    if not identity:
        identity = AuthIdentity(user_id=user.id, provider="yandex", provider_subject=subject)
    identity.verified_attributes = profile
    identity.updated_at = utc_now()
    session.add(identity)
    response = _redirect(pending.return_path)
    if pending.purpose == "login":
        user.last_login_at = utc_now()
        user.updated_at = utc_now()
        if not user.name_edited and profile["display_name"]:
            user.display_name = profile["display_name"]
        session.add(user)
        token = secrets.token_urlsafe(48)
        session.add(LoginSession(user_id=user.id, token_hash=_digest(token),
            expires_at=utc_now() + timedelta(days=settings.auth_session_days),
            user_agent=request.headers.get("user-agent", "")[:255], ip_hash=_ip_hash(request, settings)))
        response.set_cookie(SESSION_COOKIE, token, max_age=settings.auth_session_days * 86400,
                            secure=True, httponly=True, samesite="lax", path="/")
    session.commit()
    return response
