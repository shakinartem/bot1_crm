"""add audit log and scoring

Revision ID: 001_add_audit_log_and_scoring
Revises:
Create Date: 2026-06-21 00:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "001_add_audit_log_and_scoring"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("field_name", sa.String(length=128), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["crm_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audit_log_company_id"), "audit_log", ["company_id"], unique=False)
    op.create_index(op.f("ix_audit_log_created_at"), "audit_log", ["created_at"], unique=False)

    op.add_column("companies", sa.Column("maps_score", sa.Integer(), nullable=True))
    op.add_column("companies", sa.Column("website_score", sa.Integer(), nullable=True))
    op.add_column("companies", sa.Column("digital_score", sa.Integer(), nullable=True))
    op.add_column("companies", sa.Column("digital_grade", sa.String(length=1), nullable=True))
    op.add_column("companies", sa.Column("maps_confidence", sa.String(length=32), nullable=True))
    op.add_column("companies", sa.Column("website_confidence", sa.String(length=32), nullable=True))
    op.add_column("companies", sa.Column("maps_reviews", sa.Integer(), nullable=True))
    op.add_column("companies", sa.Column("maps_rating", sa.Float(), nullable=True))
    op.create_index(op.f("ix_companies_digital_grade"), "companies", ["digital_grade"], unique=False)
    op.create_index(op.f("ix_companies_digital_score"), "companies", ["digital_score"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_companies_digital_score"), table_name="companies")
    op.drop_index(op.f("ix_companies_digital_grade"), table_name="companies")
    op.drop_column("companies", "maps_rating")
    op.drop_column("companies", "maps_reviews")
    op.drop_column("companies", "website_confidence")
    op.drop_column("companies", "maps_confidence")
    op.drop_column("companies", "digital_grade")
    op.drop_column("companies", "digital_score")
    op.drop_column("companies", "website_score")
    op.drop_column("companies", "maps_score")
    op.drop_index(op.f("ix_audit_log_created_at"), table_name="audit_log")
    op.drop_index(op.f("ix_audit_log_company_id"), table_name="audit_log")
    op.drop_table("audit_log")