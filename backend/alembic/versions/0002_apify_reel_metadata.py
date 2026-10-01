"""Store Apify reel text, engagement, and run metadata."""

from alembic import op
import sqlalchemy as sa


revision = "0002_apify_reel_metadata"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reels", sa.Column("caption", sa.Text(), nullable=False, server_default=""))
    op.add_column("reels", sa.Column("transcript", sa.Text()))
    op.add_column("reels", sa.Column("likes_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("reels", sa.Column("comments_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("reels", sa.Column("shares_count", sa.Integer()))
    op.add_column("import_jobs", sa.Column("actor_run_id", sa.String(length=128)))
    op.add_column("import_jobs", sa.Column("dataset_id", sa.String(length=128)))


def downgrade() -> None:
    op.drop_column("import_jobs", "dataset_id")
    op.drop_column("import_jobs", "actor_run_id")
    op.drop_column("reels", "shares_count")
    op.drop_column("reels", "comments_count")
    op.drop_column("reels", "likes_count")
    op.drop_column("reels", "transcript")
    op.drop_column("reels", "caption")
