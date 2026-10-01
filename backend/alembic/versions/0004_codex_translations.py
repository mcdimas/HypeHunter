"""Store Codex CLI translation batches and translated Reel fields."""

from alembic import op
import sqlalchemy as sa


revision = "0004_codex_translations"
down_revision = "0003_import_observability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reels", sa.Column("translated_hook", sa.Text(), nullable=True))
    op.add_column("reels", sa.Column("translated_script", sa.Text(), nullable=True))
    op.add_column("reels", sa.Column("translated_cta", sa.Text(), nullable=True))
    op.add_column("reels", sa.Column("translation_status", sa.String(length=32), nullable=False, server_default="pending"))
    op.add_column("reels", sa.Column("translation_error", sa.Text(), nullable=True))
    op.add_column("reels", sa.Column("translation_source_hash", sa.String(length=64), nullable=True))
    op.add_column("reels", sa.Column("translation_model", sa.String(length=128), nullable=True))
    op.add_column("reels", sa.Column("translation_reasoning_effort", sa.String(length=32), nullable=True))
    op.add_column("reels", sa.Column("translated_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_reels_translation_status", "reels", ["translation_status"])
    op.create_index("ix_reels_translation_source_hash", "reels", ["translation_source_hash"])

    op.create_table(
        "translation_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("reel_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("item_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("translated_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("model", sa.String(length=128), nullable=False, server_default="gpt-5.6-sol"),
        sa.Column("reasoning_effort", sa.String(length=32), nullable=False, server_default="medium"),
        sa.Column("prompt", sa.Text(), nullable=False, server_default=""),
        sa.Column("raw_response", sa.Text(), nullable=True),
        sa.Column("stderr", sa.Text(), nullable=True),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_translation_batches_status", "translation_batches", ["status"])


def downgrade() -> None:
    op.drop_index("ix_translation_batches_status", table_name="translation_batches")
    op.drop_table("translation_batches")
    op.drop_index("ix_reels_translation_source_hash", table_name="reels")
    op.drop_index("ix_reels_translation_status", table_name="reels")
    op.drop_column("reels", "translated_at")
    op.drop_column("reels", "translation_reasoning_effort")
    op.drop_column("reels", "translation_model")
    op.drop_column("reels", "translation_source_hash")
    op.drop_column("reels", "translation_error")
    op.drop_column("reels", "translation_status")
    op.drop_column("reels", "translated_cta")
    op.drop_column("reels", "translated_script")
    op.drop_column("reels", "translated_hook")
