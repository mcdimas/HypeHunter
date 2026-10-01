import os

import pytest
from sqlalchemy import func
from sqlmodel import Session, select

from app.database import engine
from app.models import Competitor, Reel, User


@pytest.mark.skipif(
    not os.getenv("DATABASE_URL", "").startswith("postgresql"),
    reason="PostgreSQL migration smoke test",
)
def test_demo_data_is_removed_and_identity_sequences_work() -> None:
    with Session(engine) as session:
        assert session.exec(select(func.count(Reel.id))).one() == 0
        assert session.exec(select(func.count(Competitor.id))).one() == 0

        user = User(display_name="Migration test user")
        session.add(user)
        session.flush()
        competitor = Competitor(
            user_id=user.id,
            handle="@sequence.check",
            profile_url="https://instagram.com/sequence.check",
            category="Проверка миграции",
            language="EN",
        )
        session.add(competitor)
        session.flush()

        assert competitor.id is not None
        assert competitor.id > 0
        session.rollback()
