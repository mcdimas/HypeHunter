"""Owner-only YooKassa sandbox orders, separate from real access."""
from alembic import op
import sqlalchemy as sa

revision = "0013_test_payments"
down_revision = "0012_account_preferences"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("test_payments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("provider_id", sa.String(80), unique=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("confirmation_url", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("test_access_until", sa.DateTime(timezone=True)))
    op.create_index("ix_test_payments_user_id", "test_payments", ["user_id"])


def downgrade():
    op.drop_table("test_payments")
