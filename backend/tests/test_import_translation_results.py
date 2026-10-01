import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.import_translation_results import import_translation_payload
from app.models import Competitor, Reel, TranslationBatch, User


def test_import_local_translation_payload() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(User(id=1, display_name="Test user"))
        session.flush()
        competitor = Competitor(user_id=1, handle="@local", profile_url="https://instagram.com/local")
        session.add(competitor)
        session.flush()
        reel = Reel(
            user_id=1,
            competitor_id=competitor.id,
            external_id="local-1",
            title="Original",
            hook="First sentence.",
            caption="",
            transcript="First sentence. Full source. Do it now.",
            author="@local",
            published_at=datetime.now(timezone.utc),
        )
        session.add(reel)
        session.commit()
        session.refresh(reel)
        digest = hashlib.sha256(reel.transcript.encode("utf-8")).hexdigest()
        raw_response = json.dumps(
            {"translations": [{"reel_id": reel.id, "hook": "Первое.", "script": "Полный перевод.", "cta": "Сделай."}]},
            ensure_ascii=False,
        )
        payload = {
            "batches": [
                {
                    "model": "gpt-5.6-sol",
                    "reasoning_effort": "medium",
                    "prompt": "Переведи дословно текста рилса на русский язык\nSOURCE_REELS_JSON: []",
                    "raw_response": raw_response,
                    "translations": [
                        {
                            "reel_id": reel.id,
                            "source_hash": digest,
                            "hook": "Первое.",
                            "script": "Полный перевод.",
                            "cta": "Сделай.",
                        }
                    ],
                }
            ]
        }
        assert import_translation_payload(payload, session, 1) == (1, 1)

    with Session(engine) as session:
        stored = session.exec(select(Reel)).one()
        batch = session.exec(select(TranslationBatch)).one()
        assert stored.translated_script == "Полный перевод."
        assert stored.translation_status == "completed"
        assert stored.translation_model == "gpt-5.6-sol"
        assert stored.translation_reasoning_effort == "medium"
        assert batch.status == "completed"
        assert batch.translated_count == 1
        assert batch.raw_response == raw_response
