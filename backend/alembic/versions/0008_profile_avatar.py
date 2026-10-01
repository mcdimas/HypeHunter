"""Preserve a user's chosen profile photo across Telegram sign-ins."""

from alembic import op
import sqlalchemy as sa

revision = "0008_profile_avatar"
down_revision = "0007_accounts"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("avatar_edited", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column("users", "avatar_edited")
