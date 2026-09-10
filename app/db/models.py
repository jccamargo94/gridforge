import uuid
from datetime import date as date_
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _new_id() -> str:
    return uuid.uuid4().hex


class Scenario(Base):
    __tablename__ = "scenarios"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_id)
    mode: Mapped[str] = mapped_column(String, nullable=False)
    penetration_level: Mapped[str] = mapped_column(String, nullable=False)
    units: Mapped[list] = mapped_column(JSON, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_id)
    dispatch_date: Mapped[date_] = mapped_column(Date, nullable=False)
    level: Mapped[str] = mapped_column(String, nullable=False)
    solver: Mapped[str] = mapped_column(String, default="cbc")
    compute_prices: Mapped[bool] = mapped_column(Boolean, default=True)
    scenario_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("scenarios.id"), nullable=True
    )
    nodal_network: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_id)
    case_id: Mapped[str] = mapped_column(String, ForeignKey("cases.id"), nullable=False)
    user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    visibility: Mapped[str] = mapped_column(String, default="private")
    input_grade: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    out_dir: Mapped[str | None] = mapped_column(String, nullable=True)
    dispatch_path: Mapped[str | None] = mapped_column(String, nullable=True)
    price_path: Mapped[str | None] = mapped_column(String, nullable=True)
    bess_path: Mapped[str | None] = mapped_column(String, nullable=True)
    log_path: Mapped[str | None] = mapped_column(String, nullable=True)
    marginal_plants_path: Mapped[str | None] = mapped_column(String, nullable=True)


class MetricSet(Base):
    __tablename__ = "metric_sets"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_id)
    run_id: Mapped[str] = mapped_column(String, ForeignKey("runs.id"), unique=True, nullable=False)
    rmse: Mapped[float | None] = mapped_column(Float, nullable=True)
    mae: Mapped[float | None] = mapped_column(Float, nullable=True)
    bias: Mapped[float | None] = mapped_column(Float, nullable=True)
    wape: Mapped[float | None] = mapped_column(Float, nullable=True)
    smape: Mapped[float | None] = mapped_column(Float, nullable=True)
    r2: Mapped[float | None] = mapped_column(Float, nullable=True)
    bess_charge_mwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    bess_discharge_mwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    bess_avg_soc_mwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    bess_net_revenue: Mapped[float | None] = mapped_column(Float, nullable=True)
    dispatch_mae_mw: Mapped[float | None] = mapped_column(Float, nullable=True)
    dispatch_rmse_mw: Mapped[float | None] = mapped_column(Float, nullable=True)
    reference: Mapped[str | None] = mapped_column(String, nullable=True)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class NodalResult(Base):
    __tablename__ = "nodal_results"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_id)
    run_id: Mapped[str] = mapped_column(String, ForeignKey("runs.id"), unique=True, nullable=False)
    metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    redistribution: Mapped[list | None] = mapped_column(JSON, nullable=True)
    gen_revenue_by_zone: Mapped[list | None] = mapped_column(JSON, nullable=True)
    network: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    lmp_path: Mapped[str | None] = mapped_column(String, nullable=True)
    dispatch_path: Mapped[str | None] = mapped_column(String, nullable=True)
    branch_flows_path: Mapped[str | None] = mapped_column(String, nullable=True)
    settlement_status_quo_path: Mapped[str | None] = mapped_column(String, nullable=True)
    settlement_lmp_path: Mapped[str | None] = mapped_column(String, nullable=True)
    comparison_path: Mapped[str | None] = mapped_column(String, nullable=True)
    summary_path: Mapped[str | None] = mapped_column(String, nullable=True)


class InputDataset(Base):
    __tablename__ = "input_datasets"
    __table_args__ = (
        UniqueConstraint(
            "dataset", "partition_key", name="uq_input_datasets_dataset_partition_key"
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_id)
    dataset: Mapped[str] = mapped_column(String, nullable=False)
    partition_key: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    checksum: Mapped[str | None] = mapped_column(String, nullable=True)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class RunPlan(Base):
    __tablename__ = "run_plans"
    __table_args__ = (
        UniqueConstraint("kind", "target_date", name="uq_run_plans_kind_target_date"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_id)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    target_date: Mapped[date_] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    run_id: Mapped[str | None] = mapped_column(String, ForeignKey("runs.id"), nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Tenant(Base):
    """Org/workspace a run owner can belong to (multi-tenant scoping)."""

    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_id)
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class TenantMember(Base):
    """User <-> tenant membership (composite PK; no FK to auth.users — matches
    runs.user_id, resolved app-layer from the JWT `sub`)."""

    __tablename__ = "tenant_members"

    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), primary_key=True)
    user_id: Mapped[str] = mapped_column(String, primary_key=True)


class HourlySeries(Base):
    """Narrow hourly price series table: (ts, tenant_id NULL=public, series_key,
    value, source). Dedupe comes from the two partial unique indexes (D1)."""

    __tablename__ = "hourly_series"
    __table_args__ = (
        Index(
            "uq_hourly_series_public_key",
            "series_key",
            "ts",
            "source",
            unique=True,
            postgresql_where=text("tenant_id IS NULL"),
            sqlite_where=text("tenant_id IS NULL"),
        ),
        Index(
            "uq_hourly_series_tenant_key",
            "tenant_id",
            "series_key",
            "ts",
            "source",
            unique=True,
            postgresql_where=text("tenant_id IS NOT NULL"),
            sqlite_where=text("tenant_id IS NOT NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_id)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    tenant_id: Mapped[str | None] = mapped_column(String, ForeignKey("tenants.id"), nullable=True)
    series_key: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
