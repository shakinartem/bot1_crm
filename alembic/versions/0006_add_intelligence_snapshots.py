"""add intelligence snapshots

Revision ID: 0006_add_intelligence_snapshots
Revises: 0005_add_enrichment_snapshots
Create Date: 2026-05-28
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_add_intelligence_snapshots"
down_revision = "0005_add_enrichment_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "intelligence_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("inn", sa.String(length=32), nullable=True),
        sa.Column("legal_name", sa.String(length=255), nullable=True),
        sa.Column("ogrn", sa.String(length=32), nullable=True),
        sa.Column("legal_address", sa.String(length=512), nullable=True),
        sa.Column("legal_status", sa.String(length=128), nullable=True),
        sa.Column("okved", sa.String(length=64), nullable=True),
        sa.Column("website_url", sa.String(length=512), nullable=True),
        sa.Column("website_confidence", sa.Float(), nullable=True),
        sa.Column("website_candidates_json", sa.Text(), nullable=True),
        sa.Column("parsed_contacts_json", sa.Text(), nullable=True),
        sa.Column("parsed_socials_json", sa.Text(), nullable=True),
        sa.Column("parsed_signals_json", sa.Text(), nullable=True),
        sa.Column("hypotheses_json", sa.Text(), nullable=True),
        sa.Column("ai_summary", sa.Text(), nullable=True),
        sa.Column("raw_references_json", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_intelligence_snapshots_company_id"), "intelligence_snapshots", ["company_id"], unique=False)
    op.create_index(op.f("ix_intelligence_snapshots_inn"), "intelligence_snapshots", ["inn"], unique=False)
    op.create_index(op.f("ix_intelligence_snapshots_status"), "intelligence_snapshots", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_intelligence_snapshots_status"), table_name="intelligence_snapshots")
    op.drop_index(op.f("ix_intelligence_snapshots_inn"), table_name="intelligence_snapshots")
    op.drop_index(op.f("ix_intelligence_snapshots_company_id"), table_name="intelligence_snapshots")
    op.drop_table("intelligence_snapshots")
