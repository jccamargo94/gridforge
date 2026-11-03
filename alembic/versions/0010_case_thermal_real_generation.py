"""add cases.thermal_real_generation

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-03

Opt-in ideal-level option: fix thermal plants to their real generation (Gene).
Existing rows are False.
"""

import sqlalchemy as sa

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cases",
        sa.Column(
            "thermal_real_generation",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("cases", "thermal_real_generation")
