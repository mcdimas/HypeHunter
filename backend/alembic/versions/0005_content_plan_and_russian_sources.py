"""Add content plan state and reuse Russian source transcripts."""

import hashlib
import re
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "0005_content_plan"
down_revision = "0004_codex_translations"
branch_labels = None
depends_on = None


def _source_fields(row: dict) -> tuple[str, str, str]:
    script = (row["transcript"] or row["caption"] or row["hook"] or row["title"] or "").strip()
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", script) if part.strip()]
    hook = (sentences[0] if sentences else script)[:4000]
    cta = (sentences[-1] if len(sentences) > 1 else "")[:4000]
    return hook, script[:12000], cta


def _is_russian(script: str) -> bool:
    cyrillic = len(re.findall(r"[А-Яа-яЁё]", script))
    latin = len(re.findall(r"[A-Za-z]", script))
    return cyrillic >= 20 and cyrillic >= latin


def upgrade() -> None:
    op.add_column("reels", sa.Column("content_status", sa.String(length=32), nullable=False, server_default="not_started"))
    op.create_index("ix_reels_content_status", "reels", ["content_status"])

    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, title, hook, caption, transcript FROM reels")
    ).mappings()
    now = datetime.now(timezone.utc)
    for row in rows:
        hook, script, cta = _source_fields(row)
        if not _is_russian(script):
            continue
        connection.execute(
            sa.text(
                """
                UPDATE reels
                SET translated_hook = :hook,
                    translated_script = :script,
                    translated_cta = :cta,
                    translation_status = 'completed',
                    translation_error = NULL,
                    translation_source_hash = :source_hash,
                    translation_model = 'source-ru',
                    translation_reasoning_effort = 'not_required',
                    translated_at = :translated_at
                WHERE id = :reel_id
                """
            ),
            {
                "reel_id": row["id"],
                "hook": hook,
                "script": script,
                "cta": cta,
                "source_hash": hashlib.sha256(script.encode("utf-8")).hexdigest(),
                "translated_at": now,
            },
        )

    remix_rows = connection.execute(
        sa.text(
            """
            SELECT m.id AS remix_id,
                   m.hook AS remix_hook,
                   m.script AS remix_script,
                   m.cta AS remix_cta,
                   r.title,
                   r.hook,
                   r.caption,
                   r.transcript,
                   r.translated_hook,
                   r.translated_script,
                   r.translated_cta
            FROM remixes m
            JOIN reels r ON r.id = m.source_reel_id
            WHERE r.translation_status = 'completed'
              AND r.translated_script IS NOT NULL
              AND r.translated_script <> ''
            """
        )
    ).mappings()
    for row in remix_rows:
        original_hook, original_script, original_cta = _source_fields(row)
        if (
            (row["remix_hook"] or "") != original_hook
            or (row["remix_script"] or "") != original_script
            or (row["remix_cta"] or "") != original_cta
        ):
            continue
        connection.execute(
            sa.text(
                """
                UPDATE remixes
                SET hook = :hook,
                    script = :script,
                    cta = :cta,
                    updated_at = :updated_at
                WHERE id = :remix_id
                """
            ),
            {
                "remix_id": row["remix_id"],
                "hook": row["translated_hook"] or "",
                "script": row["translated_script"] or "",
                "cta": row["translated_cta"] or "",
                "updated_at": now,
            },
        )


def downgrade() -> None:
    op.drop_index("ix_reels_content_status", table_name="reels")
    op.drop_column("reels", "content_status")
