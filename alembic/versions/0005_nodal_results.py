"""add nodal_results and cases.nodal_network

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-18
"""

import sqlalchemy as sa

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cases", sa.Column("nodal_network", sa.JSON(), nullable=True))
    op.create_table(
        "nodal_results",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("redistribution", sa.JSON(), nullable=True),
        sa.Column("gen_revenue_by_zone", sa.JSON(), nullable=True),
        sa.Column("network", sa.JSON(), nullable=True),
        sa.Column("lmp_path", sa.String(), nullable=True),
        sa.Column("dispatch_path", sa.String(), nullable=True),
        sa.Column("branch_flows_path", sa.String(), nullable=True),
        sa.Column("settlement_status_quo_path", sa.String(), nullable=True),
        sa.Column("settlement_lmp_path", sa.String(), nullable=True),
        sa.Column("comparison_path", sa.String(), nullable=True),
        sa.Column("summary_path", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", name="uq_nodal_results_run_id"),
    )


def downgrade() -> None:
    op.drop_table("nodal_results")
    op.drop_column("cases", "nodal_network")
