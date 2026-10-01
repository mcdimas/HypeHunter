"""Keep sources, add platforms and move planning to independent remixes."""

from alembic import op
import sqlalchemy as sa

revision = "0006_hype_radar"
down_revision = "0005_content_plan"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("competitors", sa.Column("platform", sa.String(16), nullable=False, server_default="reels"))
    # The same handle may exist on Instagram and Threads.
    inspector = sa.inspect(op.get_bind())
    for constraint in inspector.get_unique_constraints("competitors"):
        if constraint["column_names"] == ["handle"]:
            op.drop_constraint(constraint["name"], "competitors", type_="unique")
    for index in inspector.get_indexes("competitors"):
        if index["column_names"] == ["handle"] and index["unique"] and not index.get("duplicates_constraint"):
            op.drop_index(index["name"], table_name="competitors")
            op.create_index(index["name"], "competitors", ["handle"])
    op.create_unique_constraint("uq_competitor_platform_handle", "competitors", ["platform", "handle"])
    op.create_index("ix_competitors_platform", "competitors", ["platform"])
    op.add_column("reels", sa.Column("platform", sa.String(16), nullable=False, server_default="reels"))
    op.create_index("ix_reels_platform", "reels", ["platform"])
    for field in ("views", "likes_count", "comments_count", "duration_seconds"):
        op.alter_column("reels", field, existing_type=sa.Integer(), nullable=True)
    op.add_column("remixes", sa.Column("format", sa.String(16), nullable=False, server_default="reels"))
    op.add_column("remixes", sa.Column("production_stage", sa.String(16), nullable=False, server_default="script"))
    op.add_column("remixes", sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("remixes", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_remixes_format", "remixes", ["format"])
    op.execute("UPDATE remixes SET format='threads', production_stage='text' WHERE status='ready_for_threads'")
    op.execute("UPDATE remixes SET status='in_progress' WHERE status IN ('draft', 'ready_for_threads')")
    # Preserve explicitly planned sources, without copying the entire library.
    op.execute("""
        INSERT INTO remixes (slug, source_reel_id, title, brief, hook, script, cta,
                             thread_text, status, format, production_stage, created_at, updated_at)
        SELECT 'planned-source-' || r.id, r.id, r.title, '',
               COALESCE(r.translated_hook, ''), COALESCE(r.translated_script, ''),
               COALESCE(r.translated_cta, ''), '', r.content_status, 'reels', 'script', r.created_at, r.updated_at
        FROM reels r WHERE r.content_status IN ('ready', 'published')
          AND NOT EXISTS (SELECT 1 FROM remixes m WHERE m.source_reel_id=r.id)
    """)
    op.execute("""
        UPDATE remixes m SET status=r.content_status FROM reels r
        WHERE m.source_reel_id=r.id AND r.content_status IN ('ready', 'published')
          AND m.id=(SELECT m2.id FROM remixes m2 WHERE m2.source_reel_id=r.id ORDER BY m2.updated_at DESC, m2.id DESC LIMIT 1)
    """)
    # Historical published states stay published; their unknown actual date stays NULL.


def downgrade():
    raise RuntimeError("Restore the pre-deployment PostgreSQL backup to roll back this data migration.")
