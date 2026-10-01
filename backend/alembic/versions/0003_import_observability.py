"""Add import observability and remove demo content."""

from alembic import op
import sqlalchemy as sa


revision = "0003_import_observability"
down_revision = "0002_apify_reel_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("import_jobs", sa.Column("stage", sa.String(length=64), nullable=False, server_default="queued"))
    op.add_column(
        "import_jobs",
        sa.Column("stage_message", sa.Text(), nullable=False, server_default="Задача поставлена в очередь"),
    )
    op.add_column("import_jobs", sa.Column("progress_current", sa.Integer(), nullable=False, server_default="2"))
    op.add_column("import_jobs", sa.Column("progress_total", sa.Integer(), nullable=False, server_default="8"))
    op.add_column("import_jobs", sa.Column("debug_log", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("import_jobs", sa.Column("result_summary", sa.JSON(), nullable=False, server_default="{}"))
    op.create_index("ix_import_jobs_stage", "import_jobs", ["stage"])

    op.execute(
        sa.text(
            """
            UPDATE import_jobs
            SET stage = CASE
                    WHEN status = 'completed' AND imported_count < requested_count THEN 'partial'
                    WHEN status = 'completed' THEN 'completed'
                    WHEN status = 'failed' THEN 'failed'
                    WHEN status = 'waiting_for_token' THEN 'waiting_for_token'
                    ELSE stage
                END,
                stage_message = CASE
                    WHEN status = 'completed' AND imported_count < requested_count
                        THEN 'Импорт завершён частично. Подробности доступны в журнале.'
                    WHEN status = 'completed' THEN 'Все доступные Reels сохранены в PostgreSQL'
                    WHEN status = 'failed' THEN COALESCE(error_message, 'Импорт завершился с ошибкой')
                    WHEN status = 'waiting_for_token' THEN 'Конкурент сохранён. Для запуска нужен Apify token'
                    ELSE stage_message
                END,
                progress_current = CASE WHEN status IN ('completed', 'failed') THEN 8 ELSE progress_current END
            """
        )
    )

    op.execute(
        sa.text(
            """
            DELETE FROM app_events
            WHERE (entity_type = 'competitor' AND entity_id IN (SELECT id FROM competitors WHERE handle = '@buildwithalex'))
               OR (entity_type = 'import_job' AND entity_id IN (
                    SELECT id FROM import_jobs WHERE competitor_id IN (
                        SELECT id FROM competitors WHERE handle = '@buildwithalex'
                    )
               ))
               OR (entity_type = 'reel' AND entity_id IN (
                    SELECT id FROM reels WHERE competitor_id IN (
                        SELECT id FROM competitors WHERE handle = '@buildwithalex'
                    )
               ))
               OR (entity_type = 'remix' AND entity_id IN (
                    SELECT id FROM remixes WHERE source_reel_id IN (
                        SELECT id FROM reels WHERE competitor_id IN (
                            SELECT id FROM competitors WHERE handle = '@buildwithalex'
                        )
                    )
               ))
            """
        )
    )
    op.execute(
        sa.text(
            """
            DELETE FROM remixes
            WHERE source_reel_id IN (
                SELECT id FROM reels WHERE competitor_id IN (
                    SELECT id FROM competitors WHERE handle = '@buildwithalex'
                )
            )
            """
        )
    )
    op.execute(
        sa.text(
            "DELETE FROM reels WHERE competitor_id IN (SELECT id FROM competitors WHERE handle = '@buildwithalex')"
        )
    )
    op.execute(
        sa.text(
            "DELETE FROM import_jobs WHERE competitor_id IN (SELECT id FROM competitors WHERE handle = '@buildwithalex')"
        )
    )
    op.execute(sa.text("DELETE FROM competitors WHERE handle = '@buildwithalex'"))


def downgrade() -> None:
    op.drop_index("ix_import_jobs_stage", table_name="import_jobs")
    op.drop_column("import_jobs", "result_summary")
    op.drop_column("import_jobs", "debug_log")
    op.drop_column("import_jobs", "progress_total")
    op.drop_column("import_jobs", "progress_current")
    op.drop_column("import_jobs", "stage_message")
    op.drop_column("import_jobs", "stage")
