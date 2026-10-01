from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session, select

from .api import router
from .auth import SESSION_COOKIE, _session_for_token, router as auth_router, start_telegram_polling, validate_csrf, webhook_router
from .config import get_settings
from .database import engine
from .models import Competitor, Reel, User
from .yandex_auth import router as yandex_router
from .email_auth import router as email_router


settings = get_settings()
PRIVATE_HEADERS = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.media_root.mkdir(parents=True, exist_ok=True)
    polling = start_telegram_polling(settings)
    try:
        yield
    finally:
        if polling:
            polling[0].set()
            polling[1].join(timeout=22)


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    docs_url=None,
    openapi_url=None,
    lifespan=lifespan,
)


@app.middleware("http")
async def account_boundary(request, call_next):
    path = request.url.path
    public = path == "/api/health" or path == "/api/auth/csrf" or path in {
        "/api/auth/telegram/start", "/api/auth/telegram/status", "/api/auth/telegram/finish",
        "/api/telegram/webhook",
        "/api/auth/yandex/start", "/api/auth/yandex/callback",
        "/api/auth/email/start", "/api/auth/email/finish",
    }
    if request.method not in {"GET", "HEAD", "OPTIONS"} and path != "/api/telegram/webhook":
        try:
            validate_csrf(request, settings)
        except Exception as error:
            return JSONResponse({"detail": getattr(error, "detail", "Запрос отклонён")}, status_code=403, headers=PRIVATE_HEADERS)
    if (path.startswith("/api/") or path.startswith("/media/")) and not public:
        with Session(engine) as session:
            current = _session_for_token(session, request.cookies.get(SESSION_COOKIE, ""), settings)
            if not current:
                return JSONResponse({"detail": "Требуется вход"}, status_code=401, headers=PRIVATE_HEADERS)
            request.state.user_id = current[1].id
            if path.startswith("/media/"):
                authorized = session.exec(select(Reel.id).where(
                    Reel.user_id == current[1].id, Reel.media_path == path,
                )).first() is not None
                if not authorized:
                    authorized = session.exec(select(Competitor.id).where(
                        Competitor.user_id == current[1].id, Competitor.avatar_url == path,
                    )).first() is not None
                if not authorized:
                    authorized = session.exec(select(User.id).where(
                        User.id == current[1].id, User.avatar_path == path,
                    )).first() is not None
                if not authorized:
                    return JSONResponse({"detail": "Файл не найден"}, status_code=404, headers=PRIVATE_HEADERS)
    response = await call_next(request)
    if path.startswith("/api/") or path.startswith("/media/"):
        response.headers.update(PRIVATE_HEADERS)
    return response


app.include_router(router)
app.include_router(auth_router)
app.include_router(webhook_router)
app.include_router(yandex_router)
app.include_router(email_router)
app.mount("/media", StaticFiles(directory=settings.media_root, check_dir=False), name="media")
