"""Five lifetime trial Reels for new accounts; preserve existing accounts."""
from alembic import op
import sqlalchemy as sa

revision = "0011_free_trial"
down_revision = "0010_email_auth"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("trial_reels_limit", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("trial_reels_used", sa.Integer(), nullable=False, server_default="0"))
    # Existing accounts keep their access; future inserts get the trial.
    op.alter_column("users", "trial_reels_limit", server_default="5")
    op.add_column("import_jobs", sa.Column("trial_reels_limit", sa.Integer(), nullable=True))
    op.create_check_constraint("ck_trial_used", "users", "trial_reels_used >= 0")


def downgrade():
    op.drop_constraint("ck_trial_used", "users", type_="check")
    op.drop_column("import_jobs", "trial_reels_limit")
    op.drop_column("users", "trial_reels_used")
    op.drop_column("users", "trial_reels_limit")
