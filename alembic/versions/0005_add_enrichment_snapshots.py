"""Add enrichment snapshots table.

Revision ID: 0005_add_enrichment_snapshots
Revises: 0004_add_proposal_drafts
Create Date: 2026-05-27
"""

import sqlalchemy as sa
from alembic import op

revision = "0005_add_enrichment_snapshots"
down_revision = "0004_add_proposal_drafts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "enrichment_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("website_url", sa.String(length=512), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("page_title", sa.String(length=512), nullable=True),
        sa.Column("meta_description", sa.Text(), nullable=True),
        sa.Column("detected_links_json", sa.Text(), nullable=True),
        sa.Column("detected_socials_json", sa.Text(), nullable=True),
        sa.Column("detected_maps_json", sa.Text(), nullable=True),
        sa.Column("detected_contacts_json", sa.Text(), nullable=True),
        sa.Column("signals_json", sa.Text(), nullable=True),
        sa.Column("hypotheses_json", sa.Text(), nullable=True),
        sa.Column("ai_summary", sa.Text(), nullable=True),
        sa.Column("raw_text_excerpt", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_enrichment_snapshots_company_id", "enrichment_snapshots", ["company_id"])
    op.create_index("ix_enrichment_snapshots_status", "enrichment_snapshots", ["status"])
    op.create_index("ix_enrichment_snapshots_fetched_at", "enrichment_snapshots", ["fetched_at"])


def downgrade() -> None:
    op.drop_index("ix_enrichment_snapshots_fetched_at", table_name="enrichment_snapshots")
    op.drop_index("ix_enrichment_snapshots_status", table_name="enrichment_snapshots")
    op.drop_index("ix_enrichment_snapshots_company_id", table_name="enrichment_snapshots")
    op.drop_table("enrichment_snapshots")
