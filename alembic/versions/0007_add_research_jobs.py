"""add research jobs

Revision ID: 0007_add_research_jobs
Revises: 0006_add_intelligence_snapshots
Create Date: 2026-05-28
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_add_research_jobs"
down_revision = "0006_add_intelligence_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("job_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_research_jobs_company_id"), "research_jobs", ["company_id"], unique=False)
    op.create_index(op.f("ix_research_jobs_job_type"), "research_jobs", ["job_type"], unique=False)
    op.create_index(op.f("ix_research_jobs_priority"), "research_jobs", ["priority"], unique=False)
    op.create_index(op.f("ix_research_jobs_status"), "research_jobs", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_research_jobs_status"), table_name="research_jobs")
    op.drop_index(op.f("ix_research_jobs_priority"), table_name="research_jobs")
    op.drop_index(op.f("ix_research_jobs_job_type"), table_name="research_jobs")
    op.drop_index(op.f("ix_research_jobs_company_id"), table_name="research_jobs")
    op.drop_table("research_jobs")
