"""add hourly_series table

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-09

Narrow hourly price series storage: ts (UTC), tenant_id NULL = public,
series_key, value, source. Idempotent writes rely on two partial unique
indexes (public scope and per-tenant scope) — both dialect kwargs are
required so prod (Postgres) and tests (SQLite) stay in sync.
"""

import sqlalchemy as sa

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hourly_series",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=True),
        sa.Column("series_key", sa.String(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_hourly_series_public_key",
        "hourly_series",
        ["series_key", "ts", "source"],
        unique=True,
        postgresql_where=sa.text("tenant_id IS NULL"),
        sqlite_where=sa.text("tenant_id IS NULL"),
    )
    op.create_index(
        "uq_hourly_series_tenant_key",
        "hourly_series",
        ["tenant_id", "series_key", "ts", "source"],
        unique=True,
        postgresql_where=sa.text("tenant_id IS NOT NULL"),
        sqlite_where=sa.text("tenant_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_hourly_series_tenant_key",
        table_name="hourly_series",
        postgresql_where=sa.text("tenant_id IS NOT NULL"),
        sqlite_where=sa.text("tenant_id IS NOT NULL"),
    )
    op.drop_index(
        "uq_hourly_series_public_key",
        table_name="hourly_series",
        postgresql_where=sa.text("tenant_id IS NULL"),
        sqlite_where=sa.text("tenant_id IS NULL"),
    )
    op.drop_table("hourly_series")
