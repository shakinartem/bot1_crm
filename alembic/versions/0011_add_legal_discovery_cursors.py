"""add legal discovery cursors

Revision ID: 0011_add_legal_discovery_cursors
Revises: 0010_add_lead_fit_soft_delete_and_touch_fields
Create Date: 2026-06-12
"""

from alembic import op
import sqlalchemy as sa


revision = "0011_add_legal_discovery_cursors"
down_revision = "0010_add_lead_fit_soft_delete_and_touch_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "legal_discovery_cursors" in inspector.get_table_names():
        return
    op.create_table(
        "legal_discovery_cursors",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("okved_code", sa.String(length=32), nullable=False),
        sa.Column("niche_label", sa.String(length=255), nullable=True),
        sa.Column("query_hash", sa.String(length=255), nullable=False),
        sa.Column("current_page", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_profile_url", sa.Text(), nullable=True),
        sa.Column("last_inn", sa.String(length=32), nullable=True),
        sa.Column("last_ogrn", sa.String(length=32), nullable=True),
        sa.Column("imported_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("previewed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("reset_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "okved_code", "query_hash", name="uq_legal_discovery_cursors_query"),
    )
    op.create_index(op.f("ix_legal_discovery_cursors_okved_code"), "legal_discovery_cursors", ["okved_code"], unique=False)
    op.create_index(op.f("ix_legal_discovery_cursors_provider"), "legal_discovery_cursors", ["provider"], unique=False)
    op.create_index(op.f("ix_legal_discovery_cursors_query_hash"), "legal_discovery_cursors", ["query_hash"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "legal_discovery_cursors" not in inspector.get_table_names():
        return
    op.drop_index(op.f("ix_legal_discovery_cursors_query_hash"), table_name="legal_discovery_cursors")
    op.drop_index(op.f("ix_legal_discovery_cursors_provider"), table_name="legal_discovery_cursors")
    op.drop_index(op.f("ix_legal_discovery_cursors_okved_code"), table_name="legal_discovery_cursors")
    op.drop_table("legal_discovery_cursors")
