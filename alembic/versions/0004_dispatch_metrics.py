"""add dispatch metrics and marginal plants path

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-12
"""

import sqlalchemy as sa

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("metric_sets", sa.Column("dispatch_mae_mw", sa.Float(), nullable=True))
    op.add_column("metric_sets", sa.Column("dispatch_rmse_mw", sa.Float(), nullable=True))
    op.add_column("runs", sa.Column("marginal_plants_path", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("runs", "marginal_plants_path")
    op.drop_column("metric_sets", "dispatch_rmse_mw")
    op.drop_column("metric_sets", "dispatch_mae_mw")
