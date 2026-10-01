"""Lifetime quota, independent of deletable materials and import history."""
from fastapi import HTTPException
from sqlmodel import Session, select

from .models import ImportJob, User


def trial_user(session: Session, user_id: int) -> User:
    user = session.exec(select(User).where(User.id == user_id).with_for_update()).one()
    session.refresh(user)
    return user


def reserve_trial(session: Session, user_id: int, platform: str) -> int | None:
    # The user row lock is held until the new job is committed. Active jobs
    # reserve all remaining slots; successful imports consume them atomically.
    user = trial_user(session, user_id)
    if user.trial_reels_limit is None:
        return None
    if platform != "reels":
        raise HTTPException(403, "Бесплатный доступ включает 5 Instagram Reels. Импорт Threads пока не входит в пробный доступ.")
    remaining = max(0, user.trial_reels_limit - user.trial_reels_used)
    if not remaining:
        raise HTTPException(403, "Вы использовали 5 бесплатных Reels. Переводы и ваши черновики остаются доступны. Новые загрузки будут доступны после запуска подписок.")
    active = session.exec(select(ImportJob.id).where(
        ImportJob.user_id == user_id,
        ImportJob.status.in_(["queued", "running", "waiting_for_token"]),
    )).first()
    if active is not None:
        raise HTTPException(409, "Дождитесь завершения текущей загрузки.")
    return remaining
