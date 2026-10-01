from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.apify_import import run_apify_import
from app.config import Settings
from app.models import Competitor, ImportJob, Reel, User


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
SQLModel.metadata.create_all(engine)
with Session(engine) as session:
    session.add(User(id=1, display_name="Test user"))
    session.commit()


class FakeApifyClient:
    last_actor_input = None
    last_call_options = None

    def __init__(self, token: str):
        assert token == "test-token"

    def actor(self, actor_id: str):
        assert actor_id == "apify/instagram-reel-scraper"
        return self

    def start(self, **options):
        type(self).last_actor_input = options["run_input"]
        type(self).last_call_options = options
        return {"id": "run-123", "status": "RUNNING", "defaultDatasetId": "dataset-123"}

    def run(self, run_id: str):
        assert run_id == "run-123"
        return self

    def wait_for_finish(self, *, wait_secs: int):
        assert wait_secs == 300
        return {"id": "run-123", "status": "SUCCEEDED", "defaultDatasetId": "dataset-123"}

    def abort(self, *, gracefully: bool):
        assert gracefully is False
        return {"id": "run-123", "status": "ABORTED"}

    def dataset(self, dataset_id: str):
        assert dataset_id == "dataset-123"
        return self

    def list_items(self, limit: int):
        assert limit == 3
        return SimpleNamespace(items=[
            {
                "id": "reel-newer",
                "shortCode": "NEWER",
                "caption": "Главный hook нового Reel\n\n#ai #контент",
                "transcript": "Первое предложение из аудио. Полный оригинальный текст нового Reel. Сделай это сегодня.",
                "hashtags": ["ai", "контент"],
                "url": "https://www.instagram.com/reel/NEWER/",
                "timestamp": "2026-09-15T12:00:00.000Z",
                "ownerUsername": "nick_saraev",
                "videoPlayCount": 10420,
                "likesCount": 870,
                "commentsCount": 41,
                "videoDuration": 32.4,
                "displayUrl": "https://example.com/newer.jpg",
            },
            {
                "id": "reel-older",
                "shortCode": "OLDER",
                "caption": "Второй Reel #маркетинг",
                "timestamp": "2026-09-14T12:00:00.000Z",
                "ownerUsername": "nick_saraev",
                "videoViewCount": 8010,
                "likesCount": 600,
                "commentsCount": 22,
                "videoDuration": 27,
            },
        ])


def session_factory() -> Session:
    return Session(engine)


def test_apify_import_is_capped_and_persists_reel_metadata() -> None:
    with Session(engine) as session:
        competitor = Competitor(
            user_id=1,
            handle="@nick_saraev",
            profile_url="https://instagram.com/nick_saraev",
            category="Контент",
            language="RU",
        )
        session.add(competitor)
        session.flush()
        job = ImportJob(user_id=1, competitor_id=competitor.id, status="queued", requested_count=3)
        session.add(job)
        session.commit()
        job_id = job.id

    settings = Settings(
        database_url="sqlite://",
        media_root=".test-media",
        apify_token="test-token",
        apify_import_limit=20,
        apify_max_charge_usd=1.10,
        codex_translation_auto_start=False,
    )
    run_apify_import(
        job_id,
        settings_override=settings,
        session_factory=session_factory,
        client_factory=FakeApifyClient,
        thumbnail_cache=lambda url, external_id, media_root: f"/media/thumbnails/{external_id}.jpg" if url else None,
        profile_fetcher=lambda client, username, settings: (
            "https://example.com/avatar.jpg",
            {"actor_run_id": "profile-run-1", "dataset_id": "profile-dataset-1", "profile_found": True},
        ),
        avatar_cache=lambda url, handle, media_root: f"/media/avatars/{handle}.jpg" if url else None,
    )

    actor_input = FakeApifyClient.last_actor_input
    options = FakeApifyClient.last_call_options
    assert actor_input["resultsLimit"] == 3
    assert actor_input["username"] == ["nick_saraev"]
    assert actor_input["skipPinnedPosts"] is True
    assert actor_input["includeTranscript"] is True
    assert actor_input["includeDownloadedVideo"] is False
    assert actor_input["includeSharesCount"] is False
    assert options["max_items"] == 3
    assert str(options["max_total_charge_usd"]) == "1.1"

    with Session(engine) as session:
        imported_job = session.get(ImportJob, job_id)
        reels = session.exec(select(Reel).order_by(Reel.published_at.desc())).all()
        competitor = session.exec(select(Competitor).where(Competitor.handle == "@nick_saraev")).one()

        assert imported_job.status == "completed"
        assert imported_job.imported_count == 2
        assert imported_job.stage == "partial"
        assert imported_job.progress_current == 8
        assert imported_job.result_summary["missing_count"] == 1
        assert imported_job.result_summary["transcript_count"] == 1
        assert imported_job.result_summary["avatar_cached"] is True
        assert any(entry["stage"] == "transcription" for entry in imported_job.debug_log)
        assert imported_job.actor_run_id == "run-123"
        assert imported_job.dataset_id == "dataset-123"
        assert competitor.last_import_at is not None
        assert competitor.avatar_url == "/media/avatars/1-nick_saraev.jpg"
        assert [reel.external_id for reel in reels] == ["reel-newer", "reel-older"]
        assert reels[0].caption.startswith("Главный hook")
        assert reels[0].transcript.startswith("Первое предложение")
        assert reels[0].media_path == "/media/thumbnails/1-reel-newer.jpg"
        assert reels[0].topics == ["ai", "контент"]
        assert reels[0].views == 10420
        assert reels[0].likes_count == 870
        assert reels[0].comments_count == 41
        assert reels[0].duration_seconds == 32
        assert reels[0].published_at.replace(tzinfo=timezone.utc) == datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)


class CancelDuringWaitClient(FakeApifyClient):
    job_id: int | None = None

    def wait_for_finish(self, *, wait_secs: int):
        assert self.job_id is not None
        with Session(engine) as session:
            job = session.get(ImportJob, self.job_id)
            job.status = "cancelled"
            job.stage = "cancelled"
            job.stage_message = "Импорт остановлен пользователем"
            session.add(job)
            session.commit()
        return {"id": "run-123", "status": "SUCCEEDED", "defaultDatasetId": "dataset-123"}


def test_cancelled_import_does_not_persist_late_results() -> None:
    with Session(engine) as session:
        competitor = Competitor(
            user_id=1,
            handle="@cancel_test",
            profile_url="https://instagram.com/cancel_test",
            language="EN",
        )
        session.add(competitor)
        session.flush()
        job = ImportJob(user_id=1, competitor_id=competitor.id, status="queued", requested_count=3)
        session.add(job)
        session.commit()
        job_id = job.id
        competitor_id = competitor.id

    CancelDuringWaitClient.job_id = job_id
    settings = Settings(
        database_url="sqlite://",
        media_root=".test-media",
        apify_token="test-token",
        apify_import_limit=20,
        codex_translation_auto_start=False,
    )
    run_apify_import(
        job_id,
        settings_override=settings,
        session_factory=session_factory,
        client_factory=CancelDuringWaitClient,
        thumbnail_cache=lambda url, external_id, media_root: None,
        profile_fetcher=lambda client, username, settings: (None, {}),
        avatar_cache=lambda url, handle, media_root: None,
    )

    with Session(engine) as session:
        job = session.get(ImportJob, job_id)
        reels = session.exec(select(Reel).where(Reel.competitor_id == competitor_id)).all()
        assert job.status == "cancelled"
        assert job.actor_run_id == "run-123"
        assert reels == []


class ThreadsClient(FakeApifyClient):
    def actor(self, actor_id: str):
        assert actor_id == "webdata_labs/threads-scraper"
        return self

    def list_items(self, limit: int):
        assert limit == 1
        return SimpleNamespace(items=[{
            "type": "post", "postId": "thread-real-shape", "code": "example",
            "username": "testthreads", "text": "An original text idea.",
            "url": "https://www.threads.com/@testthreads/post/example",
            "date": "2026-09-21T12:00:00Z", "likeCount": 7, "replyCount": 2, "repostCount": 1,
        }])


def test_threads_import_upsert_preserves_draft_and_skips_media() -> None:
    from app.models import Remix
    with Session(engine) as session:
        competitor = Competitor(user_id=1, platform="threads", handle="@testthreads", profile_url="https://www.threads.com/@testthreads")
        session.add(competitor)
        session.commit()
        competitor_id = competitor.id
    settings = Settings(database_url="sqlite://", media_root=".test-media", apify_token="test-token", codex_translation_auto_start=False)

    def forbidden(*args):
        raise AssertionError("Text import must not download media or request Instagram profiles")

    for attempt in range(2):
        with Session(engine) as session:
            job = ImportJob(user_id=1, competitor_id=competitor_id, status="queued", requested_count=1)
            session.add(job)
            session.commit()
            job_id = job.id
        run_apify_import(job_id, settings_override=settings, session_factory=session_factory,
                         client_factory=ThreadsClient, thumbnail_cache=forbidden,
                         avatar_cache=forbidden, profile_fetcher=forbidden)
        with Session(engine) as session:
            job = session.get(ImportJob, job_id)
            assert job.status == "completed", job.error_message
            sources = session.exec(select(Reel).where(Reel.competitor_id == competitor_id)).all()
            assert len(sources) == 1
            source = sources[0]
            assert source.transcript is None and source.views is None and source.duration_seconds is None
            assert source.likes_count == 7 and source.shares_count == 1
            if attempt == 0:
                session.add(Remix(user_id=1, slug="threads-preserved", source_reel_id=source.id, title="My draft", script="My edited text"))
                session.commit()
            else:
                assert session.exec(select(Remix).where(Remix.slug == "threads-preserved")).one().script == "My edited text"
                assert job.result_summary["new_count"] == 0
    assert ThreadsClient.last_actor_input == {"mode": "posts", "usernames": ["testthreads"], "maxPosts": 1, "includeProfile": False}
    assert str(ThreadsClient.last_call_options["max_total_charge_usd"]) == "0.1"
