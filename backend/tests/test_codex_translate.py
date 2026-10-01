import json
from datetime import datetime, timezone

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.codex_translate import CliRunResult, run_translation_backfill
from app.config import Settings
from app.models import Competitor, Reel, TranslationBatch, User


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


def fake_codex_cli(prompt: str, schema: dict, settings: Settings) -> CliRunResult:
    assert "Переведи дословно текста рилса на русский язык" in prompt
    assert settings.codex_model == "gpt-5.6-sol"
    assert settings.codex_reasoning_effort == "medium"
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
    return CliRunResult(
        exit_code=0,
        stdout="",
        stderr="",
        response=json.dumps({"translations": translations}, ensure_ascii=False),
    )


def test_translation_backfill_chunks_reels_and_persists_cli_response() -> None:
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
        codex_model="gpt-5.6-sol",
        codex_reasoning_effort="medium",
        codex_translation_batch_size=10,
    )
    run_translation_backfill(
        user_id=1,
        settings_override=settings,
        session_factory=session_factory,
        cli_runner=fake_codex_cli,
    )

    with Session(engine) as session:
        batches = session.exec(select(TranslationBatch).order_by(TranslationBatch.id)).all()
        reels = session.exec(select(Reel).order_by(Reel.id)).all()
        assert [batch.item_count for batch in batches] == [10, 2]
        assert all(batch.status == "completed" for batch in batches)
        assert all(batch.translated_count == batch.item_count for batch in batches)
        assert all(batch.raw_response and '"translations"' in batch.raw_response for batch in batches)
        assert all(reel.translation_status == "completed" for reel in reels)
        assert all(reel.translation_model == "gpt-5.6-sol" for reel in reels)
        assert all(reel.translation_reasoning_effort == "medium" for reel in reels)
        assert all(reel.translated_script.startswith("Полный перевод") for reel in reels)
