"""Add digest settings table.

Revision ID: 0003_add_digest_settings
Revises: 0002_expand_crm_core
Create Date: 2026-05-24
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_add_digest_settings"
down_revision = "0002_expand_crm_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "digest_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("telegram_user_id", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("send_time", sa.String(length=5), nullable=False, server_default="09:00"),
        sa.Column("weekdays", sa.String(length=32), nullable=False, server_default="0,1,2,3,4"),
        sa.Column("stale_days", sa.Integer(), nullable=False, server_default="7"),
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
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_user_id"),
    )
    op.create_index("ix_digest_settings_telegram_user_id", "digest_settings", ["telegram_user_id"])


def downgrade() -> None:
    op.drop_index("ix_digest_settings_telegram_user_id", table_name="digest_settings")
    op.drop_table("digest_settings")
