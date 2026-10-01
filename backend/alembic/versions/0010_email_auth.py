"""Browser-bound email login codes; existing accounts remain unchanged."""
from alembic import op
import sqlalchemy as sa

revision = "0010_email_auth"
down_revision = "0009_yandex_oauth"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("email_challenges",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("browser_secret_hash", sa.String(64), nullable=False),
        sa.Column("code_mac", sa.String(64), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("return_path", sa.String(512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)))
    op.create_index("ix_email_challenges_expires_at", "email_challenges", ["expires_at"])


def downgrade():
    op.drop_table("email_challenges")
