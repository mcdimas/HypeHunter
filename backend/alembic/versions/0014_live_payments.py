"""One-off paid packages and import quota attribution."""
from alembic import op
import sqlalchemy as sa

revision = "0014_live_payments"
down_revision = "0013_test_payments"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("payments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("provider_id", sa.String(80), unique=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("plan", sa.String(16), nullable=False),
        sa.Column("amount", sa.String(16), nullable=False),
        sa.Column("quota", sa.Integer(), nullable=False),
        sa.Column("used", sa.Integer(), nullable=False),
        sa.Column("receipt_email", sa.String(254), nullable=False),
        sa.Column("buyer_inn", sa.String(12), nullable=False),
        sa.Column("offer_version", sa.String(32), nullable=False),
        sa.Column("confirmation_url", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("access_from", sa.DateTime(timezone=True)),
        sa.Column("access_until", sa.DateTime(timezone=True)),
        sa.Column("refunded_amount", sa.String(16), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("checked_at", sa.DateTime(timezone=True)))
    op.create_index("ix_payments_user_id", "payments", ["user_id"])
    op.add_column("import_jobs", sa.Column("payment_id", sa.String(36), sa.ForeignKey("payments.id")))


def downgrade():
    op.drop_column("import_jobs", "payment_id")
    op.drop_table("payments")
