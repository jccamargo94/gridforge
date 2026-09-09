"""Hourly price-series storage: shared upsert (D2) and the two writers.

Writer 1 (`ingest_external_window`) upserts public `bolsa_tx1`/`mpo_xm` rows
for a Bogota day window — bolsa from the year CSV (already scaled to COP/MWh
by loaders), mpo from the per-date iMAR blob. Writer 2
(`ingest_run_price_rows`) upserts 24 `ideal_marginal_price` rows
(source = run id) from a finished run's price CSV, scoped public (tenant
NULL) or to every tenant the owner belongs to (B1).

Unit conversion lives in the writers (loaders `*1e3`), never in readers
(B4). Missing/unreadable sources are logged and skipped — never raised —
so a post-solve ingest problem cannot fail a finished run (B3).

D5 ts convention: CSV naive datetimes are Bogota wall time (UTC-05:00, no
DST); everything is stored as aware UTC instants.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Sequence
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.data import loaders
from app.data.actuals import load_actual_price
from app.db.models import HourlySeries, Run, TenantMember
from app.storage import get_storage

UTC = timezone.utc
BOGOTA = ZoneInfo("America/Bogota")

XM_SOURCE = "xm"
EXTERNAL_KEYS = ("bolsa_tx1", "mpo_xm")
RUN_SERIES_KEY = "ideal_marginal_price"

logger = logging.getLogger(__name__)

# pandas empty-data and parser errors both subclass ValueError; missing files
# are OSError. Both classes of source trouble are skippable, never fatal.
_SKIP = (OSError, ValueError)


def _bogota_to_utc(day: date, hour: int) -> datetime:
    """Hour `hour` of `day` in Bogota wall time, as an aware UTC instant."""
    return datetime.combine(day, time(hour), tzinfo=BOGOTA).astimezone(UTC)


def _as_utc(value: datetime) -> datetime:
    """Normalize a ts to an aware UTC instant (naive values are treated as
    already-UTC; the Bogota wall-time interpretation is the writers' job)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def bogota_day_bounds(day: date) -> tuple[datetime, datetime]:
    """Aware UTC (start, end-exclusive) of a full Bogota calendar day."""
    return _bogota_to_utc(day, 0), _bogota_to_utc(day + timedelta(days=1), 0)


def tenant_ids_for_user(session: Session, user_id: str | None) -> list[str]:
    """Tenant memberships resolvable for a JWT `sub` (empty for system runs)."""
    if user_id is None:
        return []
    stmt = select(TenantMember.tenant_id).where(TenantMember.user_id == user_id)
    return list(session.scalars(stmt))


def _upsert_stmt(session: Session):
    dialect = session.get_bind().dialect.name
    if dialect == "sqlite":
        return sqlite_insert(HourlySeries)
    if dialect == "postgresql":
        return pg_insert(HourlySeries)
    raise ValueError(f"unsupported dialect for hourly_series upsert: {dialect}")


def _payloads(rows: Sequence[HourlySeries]) -> list[dict]:
    return [
        {
            "ts": _as_utc(r.ts),
            "tenant_id": r.tenant_id,
            "series_key": r.series_key,
            "value": float(r.value),
            "source": r.source,
        }
        for r in rows
    ]


def upsert_hourly_rows(session: Session, rows: Sequence[HourlySeries]) -> int:
    """D2 shared upsert: one statement per conflict scope, one commit.

    Public rows (tenant NULL) and tenant rows resolve different partial
    unique indexes, so each group gets its own conflict target. Idempotent:
    re-writing the same (scope, series_key, ts, source) updates `value`.
    """
    if not rows:
        return 0
    insert = _upsert_stmt(session)
    excluded = insert.excluded
    for group, index_elements, index_where in (
        (
            [r for r in rows if r.tenant_id is None],
            ["series_key", "ts", "source"],
            "tenant_id IS NULL",
        ),
        (
            [r for r in rows if r.tenant_id is not None],
            ["tenant_id", "series_key", "ts", "source"],
            "tenant_id IS NOT NULL",
        ),
    ):
        if not group:
            continue
        stmt = insert.values(_payloads(group)).on_conflict_do_update(
            index_elements=index_elements,
            index_where=text(index_where),
            set_={"value": excluded.value},
        )
        session.execute(stmt)
    session.commit()
    return len(rows)


def _external_day_rows(day: date, data_dir: str) -> list[HourlySeries]:
    """Public bolsa_tx1 + mpo_xm rows for one Bogota day; skips what is
    missing or unreadable (B3) — absent hours stay gaps, never zero."""
    rows: list[HourlySeries] = []

    try:
        frame = loaders.load_precio_bolsa(data_dir, day.year)
    except _SKIP as exc:
        logger.warning("hourly ingest: skipping bolsa_tx1 for %s (%s)", day, exc)
        frame = None
    if frame is not None:
        sub = frame[frame["datetime"].dt.date == day]
        for _, raw in sub.iterrows():
            ts = _bogota_to_utc(day, raw["datetime"].hour)
            rows.append(
                HourlySeries(
                    ts=ts,
                    tenant_id=None,
                    series_key="bolsa_tx1",
                    value=float(raw["precio_bolsa"]),
                    source=XM_SOURCE,
                )
            )

    try:
        mpo = load_actual_price(day, data_dir=data_dir)  # COP/MWh, 24 values
    except _SKIP as exc:
        logger.warning("hourly ingest: skipping mpo_xm for %s (%s)", day, exc)
        mpo = None
    if mpo is not None:
        for hour, value in enumerate(mpo):
            rows.append(
                HourlySeries(
                    ts=_bogota_to_utc(day, hour),
                    tenant_id=None,
                    series_key="mpo_xm",
                    value=float(value),
                    source=XM_SOURCE,
                )
            )
    return rows


def ingest_external_window(
    session: Session, *, start: date, end_day: date, data_dir: str = "data"
) -> int:
    """REQ-HS-02: upsert public external hourly rows over Bogota days
    [start, end_day]. Returns the number of rows written (new + updated)."""
    rows: list[HourlySeries] = []
    day = start
    while day <= end_day:
        rows.extend(_external_day_rows(day, data_dir))
        day += timedelta(days=1)
    return upsert_hourly_rows(session, rows)


def _run_price_rows(run: Run) -> list[tuple[datetime, float]]:
    """(ts UTC, value COP/MWh) pairs from a run's price CSV. Naive datetimes
    in the CSV are Bogota wall time (D5); the values are already COP/MWh, so
    no unit conversion happens here (B4)."""
    if run.price_path is None:
        return []
    try:
        with get_storage(".").open(run.price_path) as f:
            frame = pd.read_csv(f, parse_dates=["datetime"])
    except _SKIP as exc:
        logger.warning("run ingest: skipping price rows for run %s (%s)", run.id, exc)
        return []
    pairs = []
    for _, raw in frame.iterrows():
        value = raw["ideal_marginal_price"]
        if pd.isna(value):
            continue
        ts = raw["datetime"]
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=BOGOTA).astimezone(UTC)
        else:
            ts = ts.astimezone(UTC)
        pairs.append((ts, float(value)))
    return pairs


def ingest_run_price_rows(session: Session, run: Run) -> int:
    """REQ-HS-03: upsert the run's 24 `ideal_marginal_price` hourly rows
    (source = run id) from its price CSV.

    Tenant attribution (B1): public runs write tenant NULL; private runs
    write under EVERY tenant the owner belongs to; an owner with zero
    memberships writes nothing — a private run can never leak public rows.
    Missing/unreadable price CSVs are skipped (B3): the run stays done.
    """
    pairs = _run_price_rows(run)
    if not pairs:
        return 0
    if run.visibility == "public":
        scopes: list[str | None] = [None]
    else:
        scopes = tenant_ids_for_user(session, run.user_id)
    rows = [
        HourlySeries(
            ts=ts,
            tenant_id=scope,
            series_key=RUN_SERIES_KEY,
            value=value,
            source=run.id,
        )
        for scope in scopes
        for ts, value in pairs
    ]
    return upsert_hourly_rows(session, rows)
