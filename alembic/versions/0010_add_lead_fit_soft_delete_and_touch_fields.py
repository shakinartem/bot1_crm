"""add lead fit soft delete and touch fields

Revision ID: 0010_add_lead_fit_soft_delete_and_touch_fields
Revises: 0009_add_crm_users_and_assignments
Create Date: 2026-06-12
"""

from alembic import op
import sqlalchemy as sa


revision = "0010_add_lead_fit_soft_delete_and_touch_fields"
down_revision = "0009_add_crm_users_and_assignments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("companies") as batch_op:
        batch_op.add_column(sa.Column("deleted_by_user_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("lead_fit_score", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("lead_fit_group", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("lead_fit_calculated_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_foreign_key(
            "fk_companies_deleted_by_user_id_crm_users",
            "crm_users",
            ["deleted_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(op.f("ix_companies_deleted_at"), ["deleted_at"], unique=False)
        batch_op.create_index(op.f("ix_companies_lead_fit_group"), ["lead_fit_group"], unique=False)
        batch_op.create_index(op.f("ix_companies_lead_fit_score"), ["lead_fit_score"], unique=False)

    with op.batch_alter_table("tasks") as batch_op:
        batch_op.add_column(sa.Column("interaction_stage", sa.String(length=64), nullable=True))
        batch_op.create_index(op.f("ix_tasks_interaction_stage"), ["interaction_stage"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.drop_index(op.f("ix_tasks_interaction_stage"))
        batch_op.drop_column("interaction_stage")

    with op.batch_alter_table("companies") as batch_op:
        batch_op.drop_index(op.f("ix_companies_lead_fit_score"))
        batch_op.drop_index(op.f("ix_companies_lead_fit_group"))
        batch_op.drop_index(op.f("ix_companies_deleted_at"))
        batch_op.drop_constraint("fk_companies_deleted_by_user_id_crm_users", type_="foreignkey")
        batch_op.drop_column("deleted_at")
        batch_op.drop_column("lead_fit_calculated_at")
        batch_op.drop_column("lead_fit_group")
        batch_op.drop_column("lead_fit_score")
        batch_op.drop_column("deleted_by_user_id")
