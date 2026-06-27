"""add company checko profile url

Revision ID: 0012_add_company_checko_profile_url
Revises: 0011_add_legal_discovery_cursors
Create Date: 2026-06-12
"""

from alembic import op
import sqlalchemy as sa


revision = "0012_add_company_checko_profile_url"
down_revision = "0011_add_legal_discovery_cursors"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("companies")}
    if "checko_profile_url" in columns:
        return
    with op.batch_alter_table("companies") as batch_op:
        batch_op.add_column(sa.Column("checko_profile_url", sa.String(length=512), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("companies")}
    if "checko_profile_url" not in columns:
        return
    with op.batch_alter_table("companies") as batch_op:
        batch_op.drop_column("checko_profile_url")
