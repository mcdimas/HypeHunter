"""Exercise the browser + Telegram handshake without contacting Telegram."""

import importlib
import io
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from PIL import Image
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.config import Settings, get_settings
from app.database import get_session
from app.models import AuthChallenge, AuthIdentity, Competitor, ImportJob, Reel, TelegramUpdate, TranslationBatch, User, utc_now


@pytest.fixture
def auth_app(monkeypatch, tmp_path):
    pg_test_url = os.getenv("AUTH_PG_TEST_URL", "")
    engine = (create_engine(pg_test_url) if pg_test_url else create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    ))
    SQLModel.metadata.create_all(engine)
    settings = Settings(
        database_url="sqlite://", public_origin="https://testserver", media_root=tmp_path,
        telegram_bot_token="fake-bot-token", telegram_bot_username="test_auth_bot",
        telegram_webhook_secret="test-webhook-secret", auth_code_secret="test-code-secret-longer-than-thirty-two-characters",
    )
    auth = importlib.import_module("app.auth")
    main = importlib.import_module("app.main")
    monkeypatch.setattr(auth, "engine", engine)
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "settings", settings)
    media = next(route.app for route in main.app.routes if getattr(route, "path", None) == "/media")
    monkeypatch.setattr(media, "directory", str(tmp_path))
    monkeypatch.setattr(media, "all_directories", [str(tmp_path)])
    monkeypatch.setattr(auth, "_telegram", lambda *args: None)
    monkeypatch.setattr(auth, "_refresh_avatar", lambda *args: None)

    def session_dependency():
        with Session(engine) as session:
            yield session

    main.app.dependency_overrides[get_session] = session_dependency
    main.app.dependency_overrides[get_settings] = lambda: settings
    yield main.app, engine
    main.app.dependency_overrides.clear()


def browser(app):
    client = TestClient(app, base_url="https://testserver")
    csrf = client.get("/api/auth/csrf")
    assert csrf.status_code == 200
    return client, {"Origin": "https://testserver", "X-CSRF-Token": csrf.json()["csrf_token"]}


def telegram(app, update, update_id):
    return TestClient(app, base_url="https://testserver").post(
        "/api/telegram/webhook", json={"update_id": update_id, **update},
        headers={"X-Telegram-Bot-Api-Secret-Token": "test-webhook-secret"},
    )


def complete_login(app, client, headers, telegram_id, first_name, update_base):
    started = client.post("/api/auth/telegram/start", json={"return_to": "/library"}, headers=headers)
    assert started.status_code == 200, started.text
    challenge = started.json()
    assert len(challenge["challenge_id"]) == 43
    assert challenge["code"] not in challenge["bot_url"]
    sender = {"id": telegram_id, "is_bot": False, "first_name": first_name}
    chat = {"id": telegram_id, "type": "private"}
    assert telegram(app, {"message": {"from": sender, "chat": chat, "text": "/start " + challenge["challenge_id"]}}, update_base).status_code == 200
    assert telegram(app, {"message": {"from": sender, "chat": chat, "text": challenge["code"]}}, update_base + 1).status_code == 200
    assert telegram(app, {"callback_query": {"id": str(update_base), "from": sender, "message": {"chat": chat},
        "data": "yes:" + challenge["challenge_id"]}}, update_base + 2).status_code == 200
    assert client.get("/api/auth/telegram/status", params={"challenge_id": challenge["challenge_id"]}).json()["state"] == "approved"
    finished = client.post("/api/auth/telegram/finish", json={"challenge_id": challenge["challenge_id"]}, headers=headers)
    assert finished.status_code == 200, finished.text
    assert finished.json()["return_to"] == "/library"
    return challenge


def test_first_login_repeat_logout_and_isolation(auth_app):
    app, engine = auth_app
    first, headers = browser(app)
    assert first.get("/api/competitors").status_code == 401
    challenge = complete_login(app, first, headers, 10101, "First", 100)
    me = first.get("/api/auth/me").json()
    assert me["display_name"] == "First"
    with Session(engine) as session:
        assert len(session.exec(select(User)).all()) == 1
        assert len(session.exec(select(AuthIdentity)).all()) == 1
        competitor = Competitor(user_id=me["id"], handle="@first", profile_url="https://instagram.com/first")
        session.add(competitor)
        session.flush()
        session.add(Reel(user_id=me["id"], competitor_id=competitor.id, external_id="private-source",
                         title="Private source", hook="Private text", author="@first",
                         media_path="/media/thumbnails/private-source.jpg"))
        session.add(ImportJob(user_id=me["id"], competitor_id=competitor.id, status="completed"))
        session.add(TranslationBatch(
            user_id=me["id"], status="completed", prompt="private prompt",
            raw_response="private raw response", stderr="private diagnostics",
        ))
        session.commit()
    assert len(first.get("/api/competitors").json()) == 1
    own_batch = first.get("/api/translations").json()["batches"][0]
    assert not {"prompt", "raw_response", "stderr"}.intersection(own_batch)
    restarted = TestClient(app, base_url="https://testserver", cookies=dict(first.cookies))
    assert restarted.get("/api/auth/me").json()["id"] == me["id"]
    assert first.post("/api/auth/telegram/finish", json={"challenge_id": challenge["challenge_id"]}, headers=headers).status_code == 403

    second, second_headers = browser(app)
    complete_login(app, second, second_headers, 20202, "Second", 200)
    assert second.get("/api/competitors").json() == []
    assert second.get("/api/reels").json()["total"] == 0
    assert second.get("/api/imports").json() == []
    assert second.get("/api/translations").json()["batches"] == []
    assert second.get("/media/thumbnails/private-source.jpg").status_code == 404
    assert second.get("/api/auth/me").json()["id"] != me["id"]
    assert second.get("/api/competitors/1").status_code == 405  # no detail route
    assert second.patch("/api/competitors/1", json={"category": "stolen"}, headers=second_headers).status_code == 404
    assert second.post("/api/remixes", json={"source_reel_id": 1}, headers=second_headers).status_code == 404
    assert first.post("/api/auth/logout", headers=headers).status_code == 200
    assert first.get("/api/competitors").status_code == 401
    complete_login(app, first, headers, 10101, "First", 300)
    assert first.get("/api/auth/me").json()["id"] == me["id"]
    assert len(first.get("/api/competitors").json()) == 1
    another, another_headers = browser(app)
    complete_login(app, another, another_headers, 10101, "First", 600)
    assert another.get("/api/auth/me").json()["id"] == me["id"]
    assert first.post("/api/auth/logout-all", headers=headers).status_code == 200
    assert first.get("/api/auth/me").status_code == 401
    assert another.get("/api/auth/me").status_code == 401


def test_csrf_survives_another_tab_and_private_errors_are_not_cached(auth_app):
    app, _ = auth_app
    client, headers = browser(app)
    second_tab = client.get("/api/auth/csrf")
    assert second_tab.json()["csrf_token"] == headers["X-CSRF-Token"]
    assert "set-cookie" not in second_tab.headers
    assert client.post("/api/auth/telegram/start", json={}, headers=headers).status_code == 200
    for response in [
        client.get("/api/competitors"),
        client.get("/media/avatars/1/private.jpg"),
        client.post("/api/auth/telegram/start", json={}),
    ]:
        assert response.status_code in {401, 403}
        assert response.headers["cache-control"] == "private, no-store"
        assert response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.skipif(not os.getenv("AUTH_PG_TEST_URL"), reason="PostgreSQL row-lock race test")
def test_parallel_draft_save_rejects_outdated_revision(auth_app, monkeypatch):
    import threading
    import time
    from sqlalchemy import event

    app, engine = auth_app
    client, headers = browser(app)
    complete_login(app, client, headers, 91919, "Draft race", 2200)
    draft = client.post("/api/remixes", json={"title": "Concurrent draft"}, headers=headers).json()
    # Hold the first reader just after SELECT. Without FOR UPDATE, both read the
    # same revision and both succeed; with the lock the second sees the new one.
    first_read = threading.Event()

    def pause_first_reader(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().startswith("SELECT") and "FROM remixes" in statement and not first_read.is_set():
            first_read.set()
            time.sleep(0.15)

    event.listen(engine, "after_cursor_execute", pause_first_reader)
    def save(title):
        clone = TestClient(app, base_url="https://testserver", cookies=dict(client.cookies))
        return clone.patch("/api/remixes/" + draft["slug"], headers=headers,
            json={"title": title, "expected_updated_at": draft["updated_at"]}).status_code

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(save, "First edit")
            assert first_read.wait(3)
            second = pool.submit(save, "Second edit")
            assert sorted([first.result(), second.result()]) == [200, 409]
    finally:
        event.remove(engine, "after_cursor_execute", pause_first_reader)


def test_profile_validation_persistence_and_private_photo(auth_app):
    app, engine = auth_app
    first, headers = browser(app)
    complete_login(app, first, headers, 81818, "Profile original", 1800)
    user_id = first.get("/api/auth/me").json()["id"]
    assert first.patch("/api/auth/profile", json={"display_name": "   "}, headers=headers).status_code == 422
    assert first.patch("/api/auth/profile", json={"display_name": "a" * 81}, headers=headers).status_code == 422
    assert first.patch("/api/auth/profile", json={"display_name": "Name", "user_id": 1}, headers=headers).status_code == 422
    assert first.patch("/api/auth/profile", json={"display_name": "Name"}).status_code == 403
    assert first.patch("/api/auth/profile", json={"display_name": "  My   studio "}, headers=headers).json() == {"display_name": "My studio"}
    assert first.get("/api/auth/me").json()["display_name"] == "My studio"
    assert first.get("/api/auth/me").json()["email"] is None

    photo = io.BytesIO()
    Image.new("RGB", (48, 32), color="#8066ff").save(photo, format="PNG")
    upload_headers = {**headers, "Content-Type": "image/png"}
    assert first.put("/api/auth/profile/avatar", content=b"<svg/>", headers=upload_headers).status_code == 422
    assert first.put("/api/auth/profile/avatar", content=b"bad", headers={**headers, "Content-Type": "image/svg+xml"}).status_code == 415
    assert first.put("/api/auth/profile/avatar", content=b"x" * (2 * 1024 * 1024 + 1), headers=upload_headers).status_code == 413
    uploaded = first.put("/api/auth/profile/avatar", content=photo.getvalue(), headers=upload_headers)
    assert uploaded.status_code == 200, uploaded.text
    path = uploaded.json()["avatar_path"]
    assert path.startswith(f"/media/avatars/{user_id}/custom-")
    own_photo = first.get(path)
    assert own_photo.status_code == 200
    assert own_photo.headers["cache-control"] == "private, no-store"
    with Image.open(io.BytesIO(own_photo.content)) as image:
        assert image.size == (512, 512)
        assert image.format == "JPEG"
    assert TestClient(app, base_url="https://testserver").get(path).status_code == 401

    second, second_headers = browser(app)
    complete_login(app, second, second_headers, 82828, "Other profile", 1900)
    assert second.get(path).status_code == 404
    assert second.patch("/api/auth/profile", json={"display_name": "Another name"}, headers=second_headers).status_code == 200
    assert first.get("/api/auth/me").json()["display_name"] == "My studio"
    complete_login(app, first, headers, 81818, "Updated Telegram name", 2000)
    me = first.get("/api/auth/me").json()
    assert me["display_name"] == "My studio" and me["avatar_path"] == path
    with Session(engine) as session:
        assert session.get(User, user_id).avatar_edited is True
        assert session.get(User, user_id).name_edited is True
    assert first.delete("/api/auth/profile/avatar", headers=headers).status_code == 200
    assert first.get("/api/auth/me").json()["avatar_path"] is None
    assert first.get(path).status_code == 404
    assert second.get("/api/auth/me").json()["display_name"] == "Another name"


def test_safe_login_destinations():
    from app.auth import _safe_return
    assert _safe_return("/today") == "/today"
    assert _safe_return("/account?tab=security") == "/account?tab=security"
    assert _safe_return("/library?tab=threads") == "/library?tab=threads"
    for value in ("/", "/login", "//evil.example", "https://evil.example", "/\\evil.example", "/today\n"):
        assert _safe_return(value) == "/today"


def test_wrong_code_foreign_browser_and_fake_webhook(auth_app):
    app, engine = auth_app
    first, headers = browser(app)
    other, other_headers = browser(app)
    started = first.post("/api/auth/telegram/start", json={"return_to": "https://evil.example/"}, headers=headers).json()
    challenge_id = started["challenge_id"]
    assert telegram(app, {"message": {"from": {"id": 30303, "first_name": "T"},
        "chat": {"id": 30303, "type": "private"}, "text": "/start " + challenge_id}}, 400).status_code == 200
    assert telegram(app, {"message": {"from": {"id": 90909, "first_name": "Other"},
        "chat": {"id": 90909, "type": "private"}, "text": "/start " + challenge_id}}, 401).status_code == 200
    fake = TestClient(app, base_url="https://testserver").post("/api/telegram/webhook", json={"update_id": 411})
    assert fake.status_code == 403
    assert other.get("/api/auth/telegram/status", params={"challenge_id": challenge_id}).status_code == 403
    status = first.get("/api/auth/telegram/status", params={"challenge_id": challenge_id}).json()
    assert status["state"] == "awaiting_code" and set(status) == {"state", "expires_at"}
    assert other.post("/api/auth/telegram/finish", json={"challenge_id": challenge_id}, headers=other_headers).status_code == 403
    assert first.post("/api/auth/telegram/finish", json={"challenge_id": challenge_id}, headers=headers).status_code == 409
    wrong = {"message": {"from": {"id": 30303, "first_name": "T"},
        "chat": {"id": 30303, "type": "private"}, "text": "000000"}}
    for update_id in range(402, 407):
        assert telegram(app, wrong, update_id).status_code == 200
    assert first.get("/api/auth/telegram/status", params={"challenge_id": challenge_id}).json()["state"] == "denied"
    assert first.post("/api/auth/telegram/finish", json={"challenge_id": challenge_id}, headers=headers).status_code == 409
    with Session(engine) as session:
        assert session.exec(select(AuthChallenge).where(AuthChallenge.id == challenge_id)).one().return_path == "/today"


def test_expiry_csrf_and_duplicate_updates(auth_app):
    app, engine = auth_app
    client, headers = browser(app)
    assert client.post("/api/auth/telegram/start", json={}, headers={"Origin": "https://other.example", "X-CSRF-Token": headers["X-CSRF-Token"]}).status_code == 403
    started = client.post("/api/auth/telegram/start", json={}, headers=headers).json()
    challenge_id = started["challenge_id"]
    update = {"message": {"from": {"id": 40404, "first_name": "T"},
        "chat": {"id": 40404, "type": "private"}, "text": "/start " + challenge_id}}
    assert telegram(app, update, 500).status_code == 200
    assert telegram(app, update, 500).status_code == 200
    with Session(engine) as session:
        challenge = session.get(AuthChallenge, challenge_id)
        assert challenge.state == "awaiting_code"
        challenge.expires_at = utc_now() - timedelta(seconds=1)
        session.add(challenge)
        session.commit()
    assert client.get("/api/auth/telegram/status", params={"challenge_id": challenge_id}).json()["state"] == "expired"
    assert client.post("/api/auth/telegram/finish", json={"challenge_id": challenge_id}, headers=headers).status_code == 409


def test_polling_uses_same_handshake_and_deduplicates(auth_app):
    app, engine = auth_app
    auth = importlib.import_module("app.auth")
    client, headers = browser(app)
    challenge = client.post("/api/auth/telegram/start", json={}, headers=headers).json()
    telegram_id = 60606
    sender = {"id": telegram_id, "is_bot": False, "first_name": "Polling"}
    chat = {"id": telegram_id, "type": "private"}
    updates = [
        {"update_id": 700, "message": {"from": sender, "chat": chat, "text": "/start " + challenge["challenge_id"]}},
        {"update_id": 701, "message": {"from": sender, "chat": chat, "text": challenge["code"]}},
        {"update_id": 702, "callback_query": {"id": "702", "from": sender, "message": {"chat": chat},
            "data": "yes:" + challenge["challenge_id"]}},
    ]
    settings = app.dependency_overrides[get_settings]()
    for update in updates:
        auth._process_polled_update(update, settings)
        auth._process_polled_update(update, settings)
    assert client.get("/api/auth/telegram/status", params={"challenge_id": challenge["challenge_id"]}).json()["state"] == "approved"
    assert client.post("/api/auth/telegram/finish", json={"challenge_id": challenge["challenge_id"]}, headers=headers).status_code == 200
    with Session(engine) as session:
        assert {item.update_id for item in session.exec(select(TelegramUpdate).where(
            TelegramUpdate.update_id.in_([700, 701, 702]),
        )).all()} == {700, 701, 702}


def yandex_setup(app, monkeypatch, subject="90001"):
    module = importlib.import_module("app.yandex_auth")
    settings = app.dependency_overrides[get_settings]()
    settings.yandex_client_id = "test-yandex-client"
    monkeypatch.setattr(module, "_profile", lambda *args: {
        "id": subject, "display_name": "Yandex User", "first_name": "Yandex", "last_name": "", "login": "example"})
    return module


def yandex_start(client, headers, **payload):
    from urllib.parse import urlparse, parse_qs
    response = client.post("/api/auth/yandex/start", json=payload, headers=headers)
    assert response.status_code == 200, response.text
    return parse_qs(urlparse(response.json()["authorize_url"]).query)


def yandex_finish(client, params, **extra):
    return client.get("/api/auth/yandex/callback", params={"state": params["state"][0], "code": "provider-code", **extra}, follow_redirects=False)


def test_yandex_pkce_login_repeat_and_logout(auth_app, monkeypatch):
    import base64
    import hashlib
    app, engine = auth_app
    module = yandex_setup(app, monkeypatch)
    client, headers = browser(app)
    assert client.get("/api/auth/csrf").json()["providers"]["yandex"] is True
    assert client.post("/api/auth/yandex/start", json={}).status_code == 403
    params = yandex_start(client, headers, return_to="https://evil.example")
    request_id, secret = client.cookies.get(module.COOKIE).split(".")
    verifier = module._verifier(app.dependency_overrides[get_settings](), request_id, secret)
    assert params["code_challenge"] == [base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")]
    assert params["code_challenge_method"] == ["S256"]
    result = yandex_finish(client, params)
    assert result.status_code == 303 and result.headers["location"] == "/today"
    assert "HttpOnly" in result.headers["set-cookie"] and "Secure" in result.headers["set-cookie"]
    user_id = client.get("/api/auth/me").json()["id"]
    assert client.get("/api/auth/me").json()["providers"] == ["yandex"]
    assert yandex_finish(client, params).headers["location"].startswith("/login?auth_error=")
    old_cookie = client.cookies.get("__Host-hype_session")
    assert client.post("/api/auth/logout", headers=headers).status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    params = yandex_start(client, headers)
    assert yandex_finish(client, params).status_code == 303
    assert client.get("/api/auth/me").json()["id"] == user_id
    assert client.cookies.get("__Host-hype_session") != old_cookie


def test_yandex_browser_binding_expiry_denial_and_provider_failure(auth_app, monkeypatch):
    from app.models import OAuthRequest
    app, engine = auth_app
    module = yandex_setup(app, monkeypatch)
    client, headers = browser(app)
    stranger, _ = browser(app)
    params = yandex_start(client, headers)
    assert "yandex_invalid" in yandex_finish(stranger, params).headers["location"]
    with Session(engine) as session:
        row = session.get(OAuthRequest, params["state"][0])
        assert row.state == "pending"
        row.expires_at = utc_now() - timedelta(seconds=1)
        session.add(row)
        session.commit()
    assert "yandex_expired" in yandex_finish(client, params).headers["location"]
    params = yandex_start(client, headers)
    assert "yandex_denied" in yandex_finish(client, params, error="access_denied").headers["location"]
    assert client.get("/api/auth/me").status_code == 401
    params = yandex_start(client, headers)
    monkeypatch.setattr(module, "_profile", lambda *args: (_ for _ in ()).throw(ValueError("provider failed")))
    assert "yandex_unavailable" in yandex_finish(client, params).headers["location"]


def test_yandex_link_preserves_owner_and_rejects_collision(auth_app, monkeypatch):
    from app.models import LoginSession
    app, engine = auth_app
    yandex_setup(app, monkeypatch, "90003")
    owner, headers = browser(app)
    complete_login(app, owner, headers, 90901, "Original Owner", 9100)
    user_id = owner.get("/api/auth/me").json()["id"]
    params = yandex_start(owner, headers, purpose="link")
    assert yandex_finish(owner, params).headers["location"] == "/account?tab=security"
    assert set(owner.get("/api/auth/me").json()["providers"]) == {"telegram", "yandex"}
    assert owner.get("/api/auth/me").json()["display_name"] == "Original Owner"
    stranger, stranger_headers = browser(app)
    complete_login(app, stranger, stranger_headers, 90902, "Other", 9200)
    assert "yandex_conflict" in yandex_finish(stranger, yandex_start(stranger, stranger_headers, purpose="link")).headers["location"]
    with Session(engine) as session:
        login = session.get(LoginSession, owner.get("/api/auth/me").json()["session_id"])
        login.created_at = utc_now() - timedelta(minutes=6)
        session.add(login)
        session.commit()
    assert owner.post("/api/auth/yandex/start", json={"purpose": "link"}, headers=headers).status_code == 428
    owner.post("/api/auth/logout", headers=headers)
    assert yandex_finish(owner, yandex_start(owner, headers)).status_code == 303
    assert owner.get("/api/auth/me").json()["id"] == user_id
    assert owner.get("/api/reels").json() != {"detail": "Требуется вход"}


def test_yandex_exchange_uses_header_and_verifier_and_checks_client(monkeypatch):
    from app import yandex_auth as module
    seen = []
    def provider(request):
        seen.append(request)
        return {"access_token": "private-token"} if len(seen) == 1 else {"id": "42", "client_id": "client", "display_name": "Name", "default_email": "example@ya.ru"}
    monkeypatch.setattr(module, "_json", provider)
    profile = module._profile("code", "verifier", Settings(yandex_client_id="client"))
    assert profile["id"] == "42" and profile["default_email"] == "example@ya.ru"
    assert b"code_verifier=verifier" in seen[0].data
    assert "private-token" not in seen[1].full_url
    assert seen[1].get_header("Authorization") == "OAuth private-token"
    seen.clear()
    with pytest.raises(ValueError):
        module._profile("code", "verifier", Settings(yandex_client_id="other"))


def test_yandex_email_is_profile_attribute_not_email_identity(auth_app, monkeypatch):
    app, engine = auth_app
    module = yandex_setup(app, monkeypatch, "90101")
    monkeypatch.setattr(module, "_profile", lambda *args: {
        "id": "90101", "display_name": "Name", "first_name": "Name", "default_email": "example@ya.ru"})
    client, headers = browser(app)
    params = yandex_start(client, headers)
    assert params["scope"] == ["login:info login:email"]
    assert yandex_finish(client, params).headers["location"] == "/today"
    me = client.get("/api/auth/me").json()
    assert me["email"] == "example@ya.ru"
    assert me["email_provider"] == "yandex"
    assert me["providers"] == ["yandex"]
    with Session(engine) as session:
        assert not session.exec(select(AuthIdentity).where(AuthIdentity.user_id == me["id"], AuthIdentity.provider == "email")).all()


@pytest.mark.skipif(not os.getenv("AUTH_PG_TEST_URL"), reason="PostgreSQL OAuth concurrency")
def test_yandex_parallel_callback_creates_one_identity_and_rejects_replay(auth_app, monkeypatch):
    app, engine = auth_app
    yandex_setup(app, monkeypatch, "90099")
    first, headers = browser(app)
    second, other_headers = browser(app)
    params = yandex_start(first, headers)
    other = yandex_start(second, other_headers)
    def finish(pair):
        client, query = pair
        clone = TestClient(app, base_url="https://testserver", cookies=dict(client.cookies))
        return yandex_finish(clone, query).headers["location"]
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(finish, [(first, params), (first, params), (second, other)]))
    assert results.count("/today") == 2
    assert sum("auth_error" in path for path in results) == 1
    with Session(engine) as session:
        identities = session.exec(select(AuthIdentity).where(AuthIdentity.provider == "yandex", AuthIdentity.provider_subject == "90099")).all()
        assert len(identities) == 1


@pytest.mark.skipif(not os.getenv("AUTH_PG_TEST_URL"), reason="PostgreSQL row-lock race test")
def test_parallel_finish_is_single_use_and_registration_is_unique(auth_app):
    app, engine = auth_app
    first, first_headers = browser(app)
    second, second_headers = browser(app)
    first_id = first.post("/api/auth/telegram/start", json={}, headers=first_headers).json()["challenge_id"]
    second_id = second.post("/api/auth/telegram/start", json={}, headers=second_headers).json()["challenge_id"]
    with Session(engine) as session:
        for challenge_id in (first_id, second_id):
            challenge = session.get(AuthChallenge, challenge_id)
            challenge.state = "approved"
            challenge.telegram_user_id = 50505
            challenge.telegram_profile = {"first_name": "Concurrent"}
            session.add(challenge)
        session.commit()

    def finish(original, headers, challenge_id):
        clone = TestClient(app, base_url="https://testserver", cookies=dict(original.cookies))
        return clone.post("/api/auth/telegram/finish", json={"challenge_id": challenge_id}, headers=headers).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda pair: finish(*pair), [
            (first, first_headers, first_id), (second, second_headers, second_id),
        ]))
    assert results == [200, 200]
    with Session(engine) as session:
        identities = session.exec(select(AuthIdentity).where(
            AuthIdentity.provider == "telegram", AuthIdentity.provider_subject == "50505",
        )).all()
        assert len(identities) == 1
        assert len(session.exec(select(User).where(User.id == identities[0].user_id)).all()) == 1

    third, third_headers = browser(app)
    challenge_id = third.post("/api/auth/telegram/start", json={}, headers=third_headers).json()["challenge_id"]
    with Session(engine) as session:
        challenge = session.get(AuthChallenge, challenge_id)
        challenge.state = "approved"
        challenge.telegram_user_id = 50505
        challenge.telegram_profile = {"first_name": "Concurrent"}
        session.add(challenge)
        session.commit()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: finish(third, third_headers, challenge_id), range(2)))
    assert sorted(results) == [200, 409]
