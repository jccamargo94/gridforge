"""add tenants and tenant_members tables

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-09

Tenant = org/workspace; TenantMember = user<->tenant membership resolved in
app-layer from the JWT user_id (no FK to auth.users — matches runs.user_id).
"""

import sqlalchemy as sa

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "tenant_members",
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("tenant_id", "user_id"),
    )


def downgrade() -> None:
    op.drop_table("tenant_members")
    op.drop_table("tenants")
