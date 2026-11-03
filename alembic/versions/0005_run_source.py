"""add runs.source (manual | scheduled)

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-03
"""

import sqlalchemy as sa

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "runs",
        sa.Column("source", sa.String(), nullable=False, server_default="manual"),
    )


def downgrade() -> None:
    op.drop_column("runs", "source")
