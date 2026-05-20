"""Expand CRM core.

Revision ID: 0002_expand_crm_core
Revises: 0001_initial
Create Date: 2026-05-20
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_expand_crm_core"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "companies",
        sa.Column("region", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "companies",
        sa.Column("social_links", sa.Text(), nullable=True),
    )
    op.add_column(
        "companies",
        sa.Column(
            "priority",
            sa.String(length=32),
            nullable=False,
            server_default="medium",
        ),
    )
    op.create_index("ix_companies_region", "companies", ["region"])
    op.create_index("ix_companies_priority", "companies", ["priority"])

    op.add_column(
        "decision_makers",
        sa.Column("source", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "decision_makers",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
    )
    op.add_column(
        "decision_makers",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
    )
    op.create_index("ix_decision_makers_full_name", "decision_makers", ["full_name"])

    op.create_table(
        "contact_points",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("value", sa.String(length=255), nullable=False),
        sa.Column("label", sa.String(length=128), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
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
    op.create_index("ix_contact_points_company_id", "contact_points", ["company_id"])
    op.create_index("ix_contact_points_type", "contact_points", ["type"])
    op.create_index("ix_contact_points_value", "contact_points", ["value"])

    with op.batch_alter_table("lead_interactions") as batch_op:
        batch_op.add_column(sa.Column("decision_maker_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("next_action", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("next_action_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("created_by", sa.String(length=128), nullable=True))
        batch_op.create_foreign_key(
            "fk_lead_interactions_decision_maker_id",
            "decision_makers",
            ["decision_maker_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index("ix_lead_interactions_decision_maker_id", "lead_interactions", ["decision_maker_id"])
    op.create_index("ix_lead_interactions_type", "lead_interactions", ["type"])
    op.create_index("ix_lead_interactions_result", "lead_interactions", ["result"])

    op.add_column(
        "tasks",
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "tasks",
        sa.Column(
            "priority",
            sa.String(length=32),
            nullable=False,
            server_default="medium",
        ),
    )
    op.add_column(
        "tasks",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_tasks_due_at", "tasks", ["due_at"])
    op.create_index("ix_tasks_status", "tasks", ["status"])
    op.create_index("ix_tasks_priority", "tasks", ["priority"])


def downgrade() -> None:
    op.drop_index("ix_tasks_priority", table_name="tasks")
    op.drop_index("ix_tasks_status", table_name="tasks")
    op.drop_index("ix_tasks_due_at", table_name="tasks")
    op.drop_column("tasks", "completed_at")
    op.drop_column("tasks", "priority")
    op.drop_column("tasks", "due_at")

    op.drop_index("ix_lead_interactions_result", table_name="lead_interactions")
    op.drop_index("ix_lead_interactions_type", table_name="lead_interactions")
    op.drop_index("ix_lead_interactions_decision_maker_id", table_name="lead_interactions")
    with op.batch_alter_table("lead_interactions") as batch_op:
        batch_op.drop_constraint("fk_lead_interactions_decision_maker_id", type_="foreignkey")
        batch_op.drop_column("created_by")
        batch_op.drop_column("next_action_at")
        batch_op.drop_column("next_action")
        batch_op.drop_column("decision_maker_id")

    op.drop_table("contact_points")

    op.drop_index("ix_decision_makers_full_name", table_name="decision_makers")
    op.drop_column("decision_makers", "updated_at")
    op.drop_column("decision_makers", "created_at")
    op.drop_column("decision_makers", "source")

    op.drop_index("ix_companies_priority", table_name="companies")
    op.drop_index("ix_companies_region", table_name="companies")
    op.drop_column("companies", "priority")
    op.drop_column("companies", "social_links")
    op.drop_column("companies", "region")
