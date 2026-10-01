import argparse
import json
from pathlib import Path
from typing import Any

from sqlmodel import Session

from .codex_translate import source_hash
from .database import engine
from .models import Reel, TranslationBatch
from .services import record_event, utc_now


EXPECTED_MODEL = "gpt-5.6-sol"
EXPECTED_REASONING_EFFORT = "medium"


def _required_string(value: Any, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} должно быть строкой")
    if not allow_empty and not value.strip():
        raise ValueError(f"{field} не должно быть пустым")
    return value


def import_translation_payload(payload: dict[str, Any], session: Session, user_id: int) -> tuple[int, int]:
    batches = payload.get("batches")
    if not isinstance(batches, list) or not batches:
        raise ValueError("В файле отсутствует непустой массив batches")

    seen_reel_ids: set[int] = set()
    imported_count = 0
    imported_batches = 0
    now = utc_now()

    for batch_index, item in enumerate(batches, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Пачка #{batch_index} должна быть объектом")
        model = item.get("model")
        reasoning_effort = item.get("reasoning_effort")
        if model != EXPECTED_MODEL or reasoning_effort != EXPECTED_REASONING_EFFORT:
            raise ValueError(
                f"Пачка #{batch_index}: ожидались {EXPECTED_MODEL}/{EXPECTED_REASONING_EFFORT}, "
                f"получены {model}/{reasoning_effort}"
            )
        prompt = _required_string(item.get("prompt"), f"Пачка #{batch_index}: prompt")
        if "Переведи дословно текста рилса на русский язык" not in prompt:
            raise ValueError(f"Пачка #{batch_index}: отсутствует обязательная инструкция перевода")
        raw_response = _required_string(
            item.get("raw_response"), f"Пачка #{batch_index}: raw_response"
        )
        translations = item.get("translations")
        if not isinstance(translations, list) or not translations:
            raise ValueError(f"Пачка #{batch_index}: translations должен быть непустым массивом")

        validated: list[tuple[Reel, dict[str, Any]]] = []
        for translation in translations:
            if not isinstance(translation, dict) or not isinstance(translation.get("reel_id"), int):
                raise ValueError(f"Пачка #{batch_index}: у каждого перевода нужен целочисленный reel_id")
            reel_id = translation["reel_id"]
            if reel_id in seen_reel_ids:
                raise ValueError(f"Reel #{reel_id} встречается в файле повторно")
            reel = session.get(Reel, reel_id)
            if reel is None or reel.user_id != user_id:
                raise ValueError(f"Reel #{reel_id} не найден у выбранного владельца")
            expected_hash = source_hash(reel)
            if translation.get("source_hash") != expected_hash:
                raise ValueError(f"Исходный текст Reel #{reel_id} изменился после локального перевода")
            _required_string(translation.get("hook"), f"Reel #{reel_id}: hook")
            _required_string(translation.get("script"), f"Reel #{reel_id}: script")
            _required_string(translation.get("cta"), f"Reel #{reel_id}: cta", allow_empty=True)
            validated.append((reel, translation))
            seen_reel_ids.add(reel_id)

        batch = TranslationBatch(
            user_id=user_id,
            status="completed",
            reel_ids=[reel.id for reel, _ in validated],
            item_count=len(validated),
            translated_count=len(validated),
            model=EXPECTED_MODEL,
            reasoning_effort=EXPECTED_REASONING_EFFORT,
            prompt=prompt,
            raw_response=raw_response,
            stderr="Выполнено локальным Codex CLI и безопасно импортировано на сервер.",
            exit_code=0,
            started_at=now,
            completed_at=now,
            updated_at=now,
        )
        session.add(batch)
        session.flush()

        for reel, translation in validated:
            reel.translated_hook = translation["hook"]
            reel.translated_script = translation["script"]
            reel.translated_cta = translation["cta"]
            reel.translation_status = "completed"
            reel.translation_error = None
            reel.translation_source_hash = translation["source_hash"]
            reel.translation_model = EXPECTED_MODEL
            reel.translation_reasoning_effort = EXPECTED_REASONING_EFFORT
            reel.translated_at = now
            reel.updated_at = now
            session.add(reel)

        record_event(
            session,
            "translation.batch_imported",
            "translation_batch",
            batch.id,
            {
                "translated_count": len(validated),
                "execution_location": "local_codex_cli",
            },
        )
        imported_count += len(validated)
        imported_batches += 1

    session.commit()
    return imported_count, imported_batches


def main() -> None:
    parser = argparse.ArgumentParser(description="Import verified local Codex CLI translations")
    parser.add_argument("payload", type=Path)
    parser.add_argument("--user-id", type=int, required=True, help="Internal owner ID of the imported sources")
    args = parser.parse_args()
    payload = json.loads(args.payload.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Корень файла должен быть объектом")
    with Session(engine) as session:
        imported_count, imported_batches = import_translation_payload(payload, session, args.user_id)
    print(f"Imported {imported_count} translations in {imported_batches} batches")


if __name__ == "__main__":
    main()
