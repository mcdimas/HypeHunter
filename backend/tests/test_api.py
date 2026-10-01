import os
import importlib
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

os.environ.setdefault("MEDIA_ROOT", ".test-media")

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.database import get_session
from app.main import app
from app.models import Competitor, ImportJob, Reel, Remix, User
from app.services import mark_russian_source_ready


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


def seed_database() -> None:
    SQLModel.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        session.add(User(id=1, display_name="Test user", trial_reels_limit=None))
        session.flush()
        competitor = Competitor(
            user_id=1,
            handle="@buildwithalex",
            profile_url="https://instagram.com/buildwithalex",
            category="Веб-разработка",
            language="EN",
            last_import_at=now,
        )
        session.add(competitor)
        session.flush()
        session.add_all([
            Reel(
                user_id=1,
                competitor_id=competitor.id,
                external_id="test-reel-1",
                title="Build a landing page in 20 min",
                hook="Соберите первый экран за 20 минут.",
                caption="Подпись публикации.",
                transcript="Соберите первый экран за 20 минут. Уберите всё лишнее. Проверьте результат сегодня.",
                topics=["лендинг", "скорость"],
                search_text="build a landing page in 20 min соберите первый экран за 20 минут @buildwithalex лендинг скорость",
                author="@buildwithalex",
                views=128000,
                duration_seconds=42,
                published_at=now,
            ),
            Reel(
                user_id=1,
                competitor_id=competitor.id,
                external_id="test-reel-2",
                title="Stop making this layout mistake",
                hook="Эта ошибка ломает иерархию.",
                topics=["layout", "иерархия"],
                search_text="stop making this layout mistake эта ошибка ломает иерархию @buildwithalex layout иерархия",
                author="@buildwithalex",
                views=64000,
                duration_seconds=28,
                published_at=now,
            ),
        ])
        session.add(ImportJob(user_id=1, competitor_id=competitor.id, provider="seed", status="completed", imported_count=2))
        session.commit()


def override_session():
    with Session(engine) as session:
        yield session


app.dependency_overrides[get_session] = override_session
seed_database()
client = TestClient(app)


@pytest.fixture(autouse=True)
def authenticated_legacy_api(monkeypatch):
    main = importlib.import_module("app.main")
    monkeypatch.setattr(main, "_session_for_token", lambda *args, **kwargs: (SimpleNamespace(), SimpleNamespace(id=1)))
    monkeypatch.setattr(main, "validate_csrf", lambda *args, **kwargs: None)


def test_health_and_smart_reel_search() -> None:
    assert client.get("/api/health").json() == {"status": "ok", "database": "connected"}
    by_hook = client.get("/api/reels", params={"q": "ломает иерархию"})
    assert by_hook.status_code == 200
    assert by_hook.json()["total"] == 1
    assert by_hook.json()["items"][0]["title"] == "Stop making this layout mistake"

    by_topic = client.get("/api/reels", params={"q": "лендинг"})
    assert by_topic.status_code == 200
    assert by_topic.json()["total"] == 1

    translations = client.get("/api/translations")
    assert translations.status_code == 200
    assert translations.json()["summary"]["eligible"] == 1
    assert translations.json()["summary"]["translated"] == 0


def test_russian_source_is_ready_without_translation_call() -> None:
    reel = Reel(
        user_id=1,
        competitor_id=1,
        external_id="russian-source-check",
        title="Русский Reel",
        hook="Первый тезис.",
        transcript=(
            "Первый тезис сразу объясняет основную идею ролика. "
            "Затем автор подробно раскрывает сценарий на русском языке. "
            "Сохрани ролик и примени совет сегодня."
        ),
        author="@russian",
    )
    assert mark_russian_source_ready(reel) is True
    assert reel.translation_status == "completed"
    assert reel.translation_model == "source-ru"
    assert reel.translated_hook == "Первый тезис сразу объясняет основную идею ролика."
    assert reel.translated_cta == "Сохрани ролик и примени совет сегодня."


def test_competitor_is_persisted_with_waiting_import() -> None:
    response = client.post("/api/competitors", json={"account": "instagram.com/content.factory"})
    assert response.status_code == 201
    created = response.json()
    assert created["handle"] == "@content.factory"

    imports = client.get("/api/imports").json()
    assert imports[0]["competitor_id"] == created["id"]
    assert imports[0]["status"] == "waiting_for_token"
    assert imports[0]["stage"] == "waiting_for_token"
    assert imports[0]["progress_current"] == 2
    assert "debug_log" not in imports[0]


def test_empty_optional_competitor_patch_does_not_break_saved_record() -> None:
    before = client.get("/api/competitors").json()[0]
    response = client.patch(f"/api/competitors/{before['id']}", json={"category": None, "language": None, "is_active": None})
    assert response.status_code == 200
    for field in ("category", "language", "is_active"):
        assert response.json()[field] == before[field]


def test_completed_short_import_explains_missing_reels() -> None:
    imports = client.get("/api/imports").json()
    seeded = next(job for job in imports if job["provider"] == "seed")
    assert seeded["stage"] == "partial"
    assert seeded["result_summary"]["missing_count"] == 18
    assert "При сохранении потерь нет" in seeded["result_summary"]["shortfall_reason"]


def test_active_import_can_be_cancelled_idempotently() -> None:
    with Session(engine) as session:
        job = ImportJob(
            user_id=1,
            competitor_id=1,
            status="queued",
            stage="queued",
            stage_message="Задача поставлена в очередь",
            requested_count=20,
        )
        session.add(job)
        session.commit()
        job_id = job.id

    response = client.post(f"/api/imports/{job_id}/cancel")
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert response.json()["stage"] == "cancelled"
    assert response.json()["stage_message"] == "Импорт остановлен пользователем"
    assert response.json()["completed_at"] is not None
    assert "debug_log" not in response.json()

    repeated = client.post(f"/api/imports/{job_id}/cancel")
    assert repeated.status_code == 200
    assert repeated.json()["status"] == "cancelled"


def test_remix_crud_rewrite_and_thread_preparation() -> None:
    response = client.post("/api/remixes", json={"source_reel_id": 1})
    assert response.status_code == 201
    remix = response.json()
    slug = remix["slug"]
    assert remix["source_reel"]["id"] == 1
    assert remix["hook"] == "Соберите первый экран за 20 минут."
    assert remix["script"] == remix["source_reel"]["transcript"]
    assert remix["cta"] == "Проверьте результат сегодня."

    updated = client.patch(
        f"/api/remixes/{slug}",
        json={"brief": "фильтрация библиотеки", "thread_text": "Черновик Threads"},
    )
    assert updated.status_code == 200
    assert updated.json()["brief"] == "фильтрация библиотеки"

    rewritten = client.post(f"/api/remixes/{slug}/rewrite")
    assert rewritten.status_code == 409
    rewritten = client.post(f"/api/remixes/{slug}/rewrite?confirm=true")
    assert rewritten.status_code == 200
    assert rewritten.json()["script"] == remix["source_reel"]["transcript"]

    prepared = client.post(f"/api/remixes/{slug}/prepare-thread")
    assert prepared.status_code == 409
    client.patch(f"/api/remixes/{slug}", json={"hook": "Новый авторский хук", "script": "Моя текущая редакция"})
    prepared = client.post(f"/api/remixes/{slug}/prepare-thread?confirm=true")
    assert prepared.status_code == 200
    assert prepared.json()["status"] == "idea"
    assert "Моя текущая редакция" in prepared.json()["thread_text"]
    assert "Новый авторский хук" in prepared.json()["thread_text"]
    derived = client.post(f"/api/remixes/{slug}/derive", json={"format": "threads"})
    assert derived.status_code == 201
    assert derived.json()["source_reel_id"] == 1
    assert derived.json()["script"] == "Моя текущая редакция"
    assert derived.json()["format"] == "threads"
    assert derived.json()["status"] == "idea"


def test_drafts_have_independent_plans_and_revision_guard() -> None:
    first = client.post("/api/remixes", json={"source_reel_id": 1}).json()
    second = client.post("/api/remixes", json={"source_reel_id": 1, "format": "threads"}).json()
    changed = client.patch(f"/api/remixes/{first['slug']}", json={
        "status": "in_progress", "production_stage": "filming",
        "scheduled_at": "2026-10-02T15:30:00+03:00", "expected_updated_at": first["updated_at"],
    })
    assert changed.status_code == 200
    assert changed.json()["published_at"] is None
    assert client.patch(f"/api/remixes/{first['slug']}", json={
        "script": "stale", "expected_updated_at": first["updated_at"],
    }).status_code == 409
    assert client.get(f"/api/remixes/{second['slug']}").json()["status"] == "idea"
    assert client.patch(f"/api/remixes/{second['slug']}", json={"production_stage": "filming"}).status_code == 422
    assert client.patch(f"/api/remixes/{first['slug']}", json={"scheduled_at": "2026-10-02T15:30:00"}).status_code == 422
    published = client.patch(f"/api/remixes/{first['slug']}", json={"status": "published"}).json()
    assert published["published_at"] is not None
    assert published["scheduled_at"] == changed.json()["scheduled_at"]
    assert client.patch(f"/api/remixes/{first['slug']}", json={"title": None}).status_code == 422
    assert client.patch(f"/api/remixes/{first['slug']}", json={"thread_text": "x" * 501}).status_code == 422
    assert client.delete(f"/api/remixes/{first['slug']}").status_code == 204
    assert client.get(f"/api/remixes/{second['slug']}").status_code == 200


def test_threads_platform_does_not_collide_with_instagram_and_filters_all_data() -> None:
    created = client.post("/api/competitors", json={
        "account": "https://www.threads.com/@buildwithalex", "platform": "threads", "requested_count": 1,
    })
    assert created.status_code == 201
    assert created.json()["platform"] == "threads"
    with Session(engine) as session:
        session.add(Reel(
            user_id=1,
            competitor_id=created.json()["id"], platform="threads", external_id="threads:api-test",
            title="A text post", hook="Original text", caption="Original text", author="@buildwithalex",
            search_text="original text @buildwithalex", translated_hook="Русская идея",
            translated_script="Русский текст", translation_status="completed", likes_count=11,
        ))
        session.commit()
    data = client.get("/api/reels", params={"platform": "threads", "q": "Русская идея", "page_size": 1, "sort": "likes"}).json()
    assert data["total"] == 1
    assert data["items"][0]["views"] is None
    assert data["items"][0]["duration_seconds"] is None
    reel_id = data["items"][0]["id"]
    draft = client.post("/api/remixes", json={"source_reel_id": reel_id}).json()
    assert draft["format"] == "threads"
    assert draft["script"] == "Русский текст"
    assert client.post("/api/competitors", json={"account": "@buildwithalex", "platform": "threads"}).status_code == 409


def test_reel_content_plan_status_can_be_updated() -> None:
    response = client.patch("/api/reels/1", json={"content_status": "ready"})
    assert response.status_code == 200
    assert response.json()["content_status"] == "ready"

    published = client.patch("/api/reels/1", json={"content_status": "published"})
    assert published.status_code == 200
    assert published.json()["content_status"] == "published"

    invalid = client.patch("/api/reels/1", json={"content_status": "unknown"})
    assert invalid.status_code == 422


def test_reel_can_be_deleted_without_deleting_its_remix() -> None:
    with Session(engine) as session:
        competitor = Competitor(
            user_id=1,
            handle="@delete.reel",
            profile_url="https://instagram.com/delete.reel",
        )
        session.add(competitor)
        session.flush()
        reel = Reel(
            user_id=1,
            competitor_id=competitor.id,
            external_id="delete-reel-source",
            title="Delete this source",
            hook="Hook",
            author=competitor.handle,
        )
        session.add(reel)
        session.flush()
        remix = Remix(user_id=1, slug="preserved-after-source-delete", source_reel_id=reel.id, title="Preserved remix")
        session.add(remix)
        session.commit()
        reel_id = reel.id
        remix_id = remix.id

    response = client.delete(f"/api/reels/{reel_id}")
    assert response.status_code == 204

    with Session(engine) as session:
        assert session.get(Reel, reel_id) is None
        preserved = session.get(Remix, remix_id)
        assert preserved is not None
        assert preserved.source_reel_id is None


def test_competitor_can_be_deleted_with_imports_and_reels() -> None:
    with Session(engine) as session:
        competitor = Competitor(
            user_id=1,
            handle="@delete.competitor",
            profile_url="https://instagram.com/delete.competitor",
        )
        session.add(competitor)
        session.flush()
        reel = Reel(
            user_id=1,
            competitor_id=competitor.id,
            external_id="delete-competitor-source",
            title="Delete competitor source",
            hook="Hook",
            author=competitor.handle,
        )
        session.add(reel)
        session.flush()
        job = ImportJob(user_id=1, competitor_id=competitor.id, provider="test", status="completed", imported_count=1)
        remix = Remix(user_id=1, slug="preserved-after-competitor-delete", source_reel_id=reel.id, title="Preserved remix")
        session.add(job)
        session.add(remix)
        session.commit()
        competitor_id = competitor.id
        reel_id = reel.id
        job_id = job.id
        remix_id = remix.id

    response = client.delete(f"/api/competitors/{competitor_id}")
    assert response.status_code == 204

    with Session(engine) as session:
        assert session.get(Competitor, competitor_id) is None
        assert session.get(Reel, reel_id) is None
        assert session.get(ImportJob, job_id) is None
        preserved = session.get(Remix, remix_id)
        assert preserved is not None
        assert preserved.source_reel_id is None
