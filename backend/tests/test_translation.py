import json
from datetime import datetime, timezone

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.translation import run_translation_backfill
from app.openai_client import TranslationResult
from app.config import Settings
from app.models import Competitor, Reel, TranslationBatch, User
from app.models import Remix
import pytest


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
SQLModel.metadata.create_all(engine)
with Session(engine) as session:
    session.add(User(id=1, display_name="Test user"))
    session.commit()


def session_factory() -> Session:
    return Session(engine)


def fake_openai(prompt: str, schema: dict, settings: Settings) -> TranslationResult:
    assert "Переведи дословно текста рилса на русский язык" in prompt
    assert settings.openai_model == "gpt-5.6-luna"
    assert schema["properties"]["translations"]["type"] == "array"
    source = json.loads(prompt.split("SOURCE_REELS_JSON:\n", 1)[1])
    translations = [
        {
            "reel_id": item["reel_id"],
            "hook": f"Хук {item['reel_id']}",
            "script": f"Полный перевод {item['reel_id']}",
            "cta": f"Действие {item['reel_id']}",
        }
        for item in source
    ]
    return TranslationResult(
        exit_code=0,
        stdout="",
        stderr="",
        response=json.dumps({"translations": translations}, ensure_ascii=False),
    )


def test_translation_backfill_chunks_reels_and_persists_api_response(monkeypatch) -> None:
    import app.auth
    monkeypatch.setattr(app.auth, "engine", engine)
    with Session(engine) as session:
        competitor = Competitor(
            user_id=1,
            handle="@translator_test",
            profile_url="https://instagram.com/translator_test",
            language="EN",
        )
        session.add(competitor)
        session.flush()
        now = datetime.now(timezone.utc)
        for index in range(12):
            session.add(
                Reel(
                    user_id=1,
                    competitor_id=competitor.id,
                    external_id=f"translation-reel-{index}",
                    title=f"Reel {index}",
                    hook=f"Hello {index}.",
                    caption="",
                    transcript=f"Hello {index}. Explain the complete idea. Do it now.",
                    author="@translator_test",
                    published_at=now,
                )
            )
        session.commit()

    settings = Settings(
        database_url="sqlite://",
        media_root=".test-media",
        openai_model="gpt-5.6-luna",
        translation_batch_size=10,
    )
    run_translation_backfill(
        user_id=1,
        settings_override=settings,
        session_factory=session_factory,
        api_runner=fake_openai,
    )

    with Session(engine) as session:
        batches = session.exec(select(TranslationBatch).order_by(TranslationBatch.id)).all()
        reels = session.exec(select(Reel).order_by(Reel.id)).all()
        assert [batch.item_count for batch in batches] == [10, 2]
        assert all(batch.status == "completed" for batch in batches)
        assert all(batch.translated_count == batch.item_count for batch in batches)
        assert all(batch.raw_response and '"translations"' in batch.raw_response for batch in batches)
        assert all(reel.translation_status == "completed" for reel in reels)
        assert all(reel.translation_model == "gpt-5.6-luna" for reel in reels)
        assert all(reel.translation_reasoning_effort == "high" for reel in reels)
        assert all(reel.translated_script.startswith("Полный перевод") for reel in reels)


@pytest.mark.parametrize("mode", ["success", "duplicate", "changed", "failure"])
def test_api_pipeline_preserves_sources_drafts_and_other_owners(monkeypatch, mode):
    import app.auth
    local_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(local_engine)
    monkeypatch.setattr(app.auth, "engine", local_engine)
    create = lambda: Session(local_engine)
    with create() as db:
        db.add(User(id=10, display_name="A"))
        db.add(User(id=11, display_name="B"))
        db.add(Competitor(id=10, user_id=10, handle="@a", profile_url="https://instagram.com/a"))
        db.add(Competitor(id=11, user_id=11, handle="@b", profile_url="https://instagram.com/b"))
        db.add(Reel(id=10, user_id=10, competitor_id=10, external_id="a", title="A", hook="A", transcript="Source A", author="@a"))
        db.add(Reel(id=11, user_id=11, competitor_id=11, external_id="b", title="B", hook="B", transcript="Source B", author="@b"))
        db.add(Remix(user_id=10, source_reel_id=10, slug="draft-a", title="My draft", script="My own edit"))
        db.commit()
    def runner(prompt, schema, config):
        assert "Source B" not in prompt
        if mode == "failure":
            raise RuntimeError("Provider unavailable")
        if mode == "changed":
            with create() as db:
                reel = db.get(Reel, 10)
                reel.transcript = "Updated source"
                db.add(reel)
                db.commit()
        item = {"reel_id": 10, "hook": "Хук", "script": "Перевод", "cta": ""}
        return TranslationResult(0, "", "", json.dumps({"translations": [item, item] if mode == "duplicate" else [item]}))
    run_translation_backfill(Settings(database_url="sqlite://"), create, runner, user_id=10)
    with create() as db:
        reel = db.get(Reel, 10)
        assert reel.transcript == ("Updated source" if mode == "changed" else "Source A")
        assert db.get(Reel, 11).translation_status == "pending"
        assert not db.get(Reel, 11).translated_script
        assert db.exec(select(Remix)).one().script == "My own edit"
        assert reel.translation_status == {"success": "completed", "duplicate": "failed", "failure": "failed", "changed": "pending"}[mode]
        if mode != "success":
            assert not reel.translated_script
