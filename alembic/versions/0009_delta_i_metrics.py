"""add dI (valor adicional) metrics to metric_sets

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-03

The model reproduces the MPO but not XM's daily additive term dI. These
columns persist the per-day dI estimate (app/pipeline/delta_i.py) and the
price error with it removed, so the UI/API can report both.
"""

import sqlalchemy as sa

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

_COLUMNS = (
    "delta_i",
    "delta_i_hours_matched",
    "rmse_ex_delta",
    "mae_ex_delta",
    "bias_ex_delta",
    "wape_ex_delta",
)


def upgrade() -> None:
    for name in _COLUMNS:
        op.add_column("metric_sets", sa.Column(name, sa.Float(), nullable=True))


def downgrade() -> None:
    for name in reversed(_COLUMNS):
        op.drop_column("metric_sets", name)
