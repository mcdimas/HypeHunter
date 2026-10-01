"""Persist personal scenario and notification preferences."""
from alembic import op
import sqlalchemy as sa

revision = "0012_account_preferences"
down_revision = "0011_free_trial"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("preferences", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))


def downgrade():
    op.drop_column("users", "preferences")
