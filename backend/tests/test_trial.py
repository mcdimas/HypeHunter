from types import SimpleNamespace
import pytest
from fastapi import BackgroundTasks, HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.api import create_competitor, create_import, delete_competitor, trial_status
from app.apify_import import run_apify_import
from app.config import Settings
from app.models import Competitor, ImportJob, Reel, User
from app.schemas import CompetitorCreate, ImportCreate
from app.trial import reserve_trial


@pytest.fixture
def trial_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([User(id=1), User(id=2), User(id=3, trial_reels_limit=None)])
        session.commit()
    yield engine
    engine.dispose()


class FakeSource:
    count = 12
    fail = False
    def __init__(self, token): pass
    def actor(self, name): return self
    def start(self, **kw):
        assert kw["run_input"]["resultsLimit"] == 20
        assert kw["max_items"] == 20
        assert kw["run_input"]["includeTranscript"]
        assert not kw["run_input"]["skipPinnedPosts"]
        if self.fail:
            raise RuntimeError("Source unavailable")
        return {"id": "trial-run"}
    def run(self, run_id): return self
    def wait_for_finish(self, **kw):
        return {"status": "SUCCEEDED", "defaultDatasetId": "trial-data"}
    def dataset(self, dataset_id): return self
    def list_items(self, limit):
        assert limit == 20
        # Older items get more views; selection must not just take newest five.
        return SimpleNamespace(items=[{
            "id": f"trial-{i}", "ownerUsername": "trial_test",
            "caption": f"Hook {i}", "transcript": f"Original source {i}. Read more.",
            "timestamp": f"2026-09-{25-i:02}T12:00:00Z",
            "videoPlayCount": i * 1000,
        } for i in range(self.count)])


def import_trial(engine, job_id, monkeypatch):
    calls = []
    monkeypatch.setattr("app.translation.run_translation_backfill", lambda **kw: calls.append(kw))
    run_apify_import(job_id, settings_override=Settings(apify_token="fake", translation_auto_start=True),
        session_factory=lambda: Session(engine), client_factory=FakeSource,
        profile_fetcher=lambda *args: (None, {}), avatar_cache=lambda *args: None,
        thumbnail_cache=lambda *args: None)
    return calls


def start_trial(engine):
    with Session(engine) as session:
        result = create_competitor(CompetitorCreate(account="trial_test", requested_count=20),
            BackgroundTasks(), session, Settings(apify_token=""), 1)
        job = session.exec(select(ImportJob).where(ImportJob.user_id == 1)).one()
        assert job.trial_reels_limit == job.requested_count == 5
        job.status = "queued"
        session.add(job)
        session.commit()
        return result.id, job.id


def test_trial_selects_top_five_translates_and_deletion_does_not_reset(trial_db, monkeypatch):
    monkeypatch.setattr(FakeSource, "count", 12)
    competitor_id, job_id = start_trial(trial_db)
    with Session(trial_db) as session:
        with pytest.raises(HTTPException) as busy:
            reserve_trial(session, 1, "reels")
        assert busy.value.status_code == 409
    calls = import_trial(trial_db, job_id, monkeypatch)
    with Session(trial_db) as session:
        reels = session.exec(select(Reel).where(Reel.user_id == 1)).all()
        assert {r.external_id for r in reels} == {f"trial-{i}" for i in range(7, 12)}
        assert calls[0]["user_id"] == 1
        assert set(calls[0]["only_ids"]) == {r.id for r in reels}
        assert trial_status(1, session) == {"limit": 5, "used": 5, "remaining": 0}
        assert trial_status(2, session)["remaining"] == 5
        assert trial_status(3, session)["limit"] is None
        with pytest.raises(HTTPException) as exhausted:
            create_import(ImportCreate(competitor_id=competitor_id, requested_count=20), BackgroundTasks(), session, Settings(), 1)
        assert exhausted.value.status_code == 403
        session.rollback()
        delete_competitor(competitor_id, session, Settings(), 1)
        assert trial_status(1, session)["used"] == 5
        with pytest.raises(HTTPException):
            reserve_trial(session, 1, "reels")


@pytest.mark.parametrize("fail,count,used,status", [(True, 12, 0, "failed"), (False, 2, 2, "completed")])
def test_failure_and_partial_import_preserve_remaining(trial_db, monkeypatch, fail, count, used, status):
    monkeypatch.setattr(FakeSource, "fail", fail)
    monkeypatch.setattr(FakeSource, "count", count)
    _, job_id = start_trial(trial_db)
    import_trial(trial_db, job_id, monkeypatch)
    with Session(trial_db) as session:
        assert session.get(ImportJob, job_id).status == status
        assert trial_status(1, session)["remaining"] == 5 - used
        assert reserve_trial(session, 1, "reels") == 5 - used
        with pytest.raises(HTTPException):
            reserve_trial(session, 2, "threads")
        assert reserve_trial(session, 3, "threads") is None
