"""add run_plans and daily-run columns

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-08

Downgrade caveat: reverting to 0005 re-adds the NOT NULL constraint on
runs.user_id and drops run_plans. Clean up first — delete any system runs
(user_id IS NULL) and all run_plans rows (FK to runs) — otherwise the
batch alter raises IntegrityError on the NOT NULL re-add.
"""

import sqlalchemy as sa

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "run_plans",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("run_id", sa.String(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kind", "target_date", name="uq_run_plans_kind_target_date"),
    )
    with op.batch_alter_table("runs") as batch:
        batch.alter_column("user_id", existing_type=sa.String(), nullable=True)
        batch.add_column(
            sa.Column("visibility", sa.String(), nullable=False, server_default="private")
        )
        batch.add_column(sa.Column("input_grade", sa.String(), nullable=True))
    with op.batch_alter_table("metric_sets") as batch:
        batch.add_column(sa.Column("reference", sa.String(), nullable=True))
        batch.add_column(sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("metric_sets") as batch:
        batch.drop_column("reference")
        batch.drop_column("evaluated_at")
    with op.batch_alter_table("runs") as batch:
        batch.drop_column("input_grade")
        batch.drop_column("visibility")
        batch.alter_column("user_id", existing_type=sa.String(), nullable=False)
    op.drop_table("run_plans")
