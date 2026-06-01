"""add company insight snapshots

Revision ID: 0008_add_company_insight_snapshots
Revises: 0007_add_research_jobs
Create Date: 2026-06-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0008_add_company_insight_snapshots"
down_revision = "0007_add_research_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "company_insight_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("insight_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=128), nullable=True),
        sa.Column("version", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_company_insight_snapshots_company_id"),
        "company_insight_snapshots",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_company_insight_snapshots_insight_type"),
        "company_insight_snapshots",
        ["insight_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_company_insight_snapshots_source"),
        "company_insight_snapshots",
        ["source"],
        unique=False,
    )
    op.create_index(
        op.f("ix_company_insight_snapshots_status"),
        "company_insight_snapshots",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_company_insight_snapshots_status"), table_name="company_insight_snapshots")
    op.drop_index(op.f("ix_company_insight_snapshots_source"), table_name="company_insight_snapshots")
    op.drop_index(op.f("ix_company_insight_snapshots_insight_type"), table_name="company_insight_snapshots")
    op.drop_index(op.f("ix_company_insight_snapshots_company_id"), table_name="company_insight_snapshots")
    op.drop_table("company_insight_snapshots")
