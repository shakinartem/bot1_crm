"""add crm users and assignments

Revision ID: 0009_add_crm_users_and_assignments
Revises: 0008_add_company_insight_snapshots
Create Date: 2026-06-02
"""

from alembic import op
import sqlalchemy as sa


revision = "0009_add_crm_users_and_assignments"
down_revision = "0008_add_company_insight_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crm_users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("telegram_user_id", sa.Integer(), nullable=True),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("role", sa.String(length=32), nullable=False, server_default="manager"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_user_id"),
    )
    op.create_index(op.f("ix_crm_users_role"), "crm_users", ["role"], unique=False)
    op.create_index(op.f("ix_crm_users_telegram_user_id"), "crm_users", ["telegram_user_id"], unique=False)

    with op.batch_alter_table("companies") as batch_op:
        batch_op.add_column(sa.Column("assigned_user_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("created_by_user_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("updated_by_user_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key("fk_companies_assigned_user_id_crm_users", "crm_users", ["assigned_user_id"], ["id"], ondelete="SET NULL")
        batch_op.create_foreign_key("fk_companies_created_by_user_id_crm_users", "crm_users", ["created_by_user_id"], ["id"], ondelete="SET NULL")
        batch_op.create_foreign_key("fk_companies_updated_by_user_id_crm_users", "crm_users", ["updated_by_user_id"], ["id"], ondelete="SET NULL")
        batch_op.create_index(op.f("ix_companies_assigned_user_id"), ["assigned_user_id"], unique=False)

    with op.batch_alter_table("tasks") as batch_op:
        batch_op.add_column(sa.Column("assigned_user_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("created_by_user_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key("fk_tasks_assigned_user_id_crm_users", "crm_users", ["assigned_user_id"], ["id"], ondelete="SET NULL")
        batch_op.create_foreign_key("fk_tasks_created_by_user_id_crm_users", "crm_users", ["created_by_user_id"], ["id"], ondelete="SET NULL")
        batch_op.create_index(op.f("ix_tasks_assigned_user_id"), ["assigned_user_id"], unique=False)

    with op.batch_alter_table("lead_interactions") as batch_op:
        batch_op.add_column(sa.Column("created_by_user_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_lead_interactions_created_by_user_id_crm_users",
            "crm_users",
            ["created_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(op.f("ix_lead_interactions_created_by_user_id"), ["created_by_user_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("lead_interactions") as batch_op:
        batch_op.drop_index(op.f("ix_lead_interactions_created_by_user_id"))
        batch_op.drop_constraint("fk_lead_interactions_created_by_user_id_crm_users", type_="foreignkey")
        batch_op.drop_column("created_by_user_id")

    with op.batch_alter_table("tasks") as batch_op:
        batch_op.drop_index(op.f("ix_tasks_assigned_user_id"))
        batch_op.drop_constraint("fk_tasks_created_by_user_id_crm_users", type_="foreignkey")
        batch_op.drop_constraint("fk_tasks_assigned_user_id_crm_users", type_="foreignkey")
        batch_op.drop_column("created_by_user_id")
        batch_op.drop_column("assigned_user_id")

    with op.batch_alter_table("companies") as batch_op:
        batch_op.drop_index(op.f("ix_companies_assigned_user_id"))
        batch_op.drop_constraint("fk_companies_updated_by_user_id_crm_users", type_="foreignkey")
        batch_op.drop_constraint("fk_companies_created_by_user_id_crm_users", type_="foreignkey")
        batch_op.drop_constraint("fk_companies_assigned_user_id_crm_users", type_="foreignkey")
        batch_op.drop_column("updated_by_user_id")
        batch_op.drop_column("created_by_user_id")
        batch_op.drop_column("assigned_user_id")

    op.drop_index(op.f("ix_crm_users_telegram_user_id"), table_name="crm_users")
    op.drop_index(op.f("ix_crm_users_role"), table_name="crm_users")
    op.drop_table("crm_users")
