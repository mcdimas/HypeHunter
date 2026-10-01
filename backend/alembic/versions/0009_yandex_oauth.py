"""Persist browser-bound, single-use Yandex OAuth requests."""
from alembic import op
import sqlalchemy as sa

revision = "0009_yandex_oauth"
down_revision = "0008_profile_avatar"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("oauth_requests",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("browser_secret_hash", sa.String(64), nullable=False),
        sa.Column("purpose", sa.String(16), nullable=False),
        sa.Column("link_session_id", sa.Integer(), sa.ForeignKey("auth_sessions.id")),
        sa.Column("return_path", sa.String(512), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)))
    op.create_index("ix_oauth_requests_expires_at", "oauth_requests", ["expires_at"])


def downgrade():
    op.drop_table("oauth_requests")
