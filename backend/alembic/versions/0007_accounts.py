"""Create accounts and assign every existing record to a verified owner."""

import os

from alembic import op
import sqlalchemy as sa


revision = "0007_accounts"
down_revision = "0006_hype_radar"
branch_labels = None
depends_on = None


def _timestamps():
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def _drop_global_unique(table: str, columns: list[str]):
    inspector = sa.inspect(op.get_bind())
    for constraint in inspector.get_unique_constraints(table):
        if constraint["column_names"] == columns:
            op.drop_constraint(constraint["name"], table, type_="unique")
    for index in inspector.get_indexes(table):
        if index["column_names"] == columns and index["unique"] and not index.get("duplicates_constraint"):
            op.drop_index(index["name"], table_name=table)


def upgrade():
    bind = op.get_bind()
    owner_id = os.getenv("OWNER_TELEGRAM_ID", "").strip()
    existing = sum(bind.execute(sa.text(f"SELECT count(*) FROM {table}")).scalar_one() for table in (
        "competitors", "reels", "remixes", "import_jobs", "translation_batches", "app_events"
    ))
    if existing and (not owner_id.isdecimal() or int(owner_id) <= 0):
        raise RuntimeError("OWNER_TELEGRAM_ID must be a verified numeric ID before migrating existing data")

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("name_edited", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("avatar_path", sa.String(1024)),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        *_timestamps(),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_users_status", "users", ["status"])
    op.create_table(
        "auth_identities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_subject", sa.String(255), nullable=False),
        sa.Column("verified_attributes", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("provider", "provider_subject", name="uq_auth_identity_provider_subject"),
    )
    op.create_index("ix_auth_identities_user_id", "auth_identities", ["user_id"])
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("user_agent", sa.String(255), nullable=False),
        sa.Column("ip_hash", sa.String(64), nullable=False),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_token_hash", "auth_sessions", ["token_hash"], unique=True)
    op.create_table(
        "auth_challenges",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("purpose", sa.String(16), nullable=False),
        sa.Column("browser_secret_hash", sa.String(64), nullable=False),
        sa.Column("code_mac", sa.String(64), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger()),
        sa.Column("telegram_profile", sa.JSON(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("return_path", sa.String(512), nullable=False),
        sa.Column("ip_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_auth_challenges_state", "auth_challenges", ["state"])
    op.create_table(
        "telegram_updates",
        sa.Column("update_id", sa.BigInteger(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "auth_rate_limits",
        sa.Column("key_hash", sa.String(64), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
    )

    if existing:
        user_id = bind.execute(sa.text("""
            INSERT INTO users (display_name, name_edited, status, created_at, updated_at)
            VALUES ('Владелец', false, 'active', now(), now()) RETURNING id
        """)).scalar_one()
        bind.execute(sa.text("""
            INSERT INTO auth_identities (user_id, provider, provider_subject, verified_attributes, created_at, updated_at)
            VALUES (:user_id, 'telegram', :subject, '{}', now(), now())
        """), {"user_id": user_id, "subject": owner_id})

    for table in ("competitors", "reels", "remixes", "import_jobs", "translation_batches", "app_events"):
        op.add_column(table, sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True))
        if existing:
            bind.execute(sa.text(f"UPDATE {table} SET user_id=:user_id"), {"user_id": user_id})
        op.alter_column(table, "user_id", existing_type=sa.Integer(), nullable=False)
        op.create_index(f"ix_{table}_user_id", table, ["user_id"])

    _drop_global_unique("competitors", ["platform", "handle"])
    _drop_global_unique("competitors", ["profile_url"])
    _drop_global_unique("reels", ["external_id"])
    op.create_unique_constraint("uq_competitor_user_platform_handle", "competitors", ["user_id", "platform", "handle"])
    op.create_unique_constraint("uq_competitor_user_profile_url", "competitors", ["user_id", "profile_url"])
    op.create_unique_constraint("uq_reel_user_external_id", "reels", ["user_id", "external_id"])

    if existing:
        for table in ("competitors", "reels", "remixes", "import_jobs", "translation_batches", "app_events"):
            if bind.execute(sa.text(f"SELECT count(*) FROM {table} WHERE user_id != :user_id OR user_id IS NULL"), {"user_id": user_id}).scalar_one():
                raise RuntimeError(f"Owner migration verification failed for {table}")


def downgrade():
    raise RuntimeError("Do not roll back to an unauthenticated release; restore a controlled backup instead.")
