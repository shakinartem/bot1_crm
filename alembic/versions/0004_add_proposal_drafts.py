"""Add proposal drafts table.

Revision ID: 0004_add_proposal_drafts
Revises: 0003_add_digest_settings
Create Date: 2026-05-25
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_add_proposal_drafts"
down_revision = "0003_add_digest_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "proposal_drafts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("draft_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("file_path", sa.String(length=512), nullable=False),
        sa.Column("selected_packages", sa.Text(), nullable=True),
        sa.Column("used_ai", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_proposal_drafts_company_id", "proposal_drafts", ["company_id"])
    op.create_index("ix_proposal_drafts_draft_type", "proposal_drafts", ["draft_type"])


def downgrade() -> None:
    op.drop_index("ix_proposal_drafts_draft_type", table_name="proposal_drafts")
    op.drop_index("ix_proposal_drafts_company_id", table_name="proposal_drafts")
    op.drop_table("proposal_drafts")
