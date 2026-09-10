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

import argparse
import logging
import os
from datetime import date, datetime, time, timedelta, timezone
from typing import Sequence
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import or_, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.data import loaders
from app.data.actuals import load_actual_price
from app.db.models import Base, HourlySeries, Run, TenantMember
from app.db.session import get_engine
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


def fetch_visible_rows(
    session: Session,
    *,
    start: date,
    end: date,
    tenant_ids: Sequence[str] = (),
) -> list[HourlySeries]:
    """REQ-HS-05: hourly rows over Bogota days [start, end] (inclusive) that
    a caller may see: public rows (tenant NULL) always, tenant rows only for
    the given tenant memberships. Ordered by ts."""
    start_utc, _ = bogota_day_bounds(start)
    _, end_utc = bogota_day_bounds(end)
    scope = [HourlySeries.tenant_id.is_(None)]
    if tenant_ids:
        scope.append(HourlySeries.tenant_id.in_(tenant_ids))
    stmt = (
        select(HourlySeries)
        .where(HourlySeries.ts >= start_utc, HourlySeries.ts < end_utc, or_(*scope))
        .order_by(HourlySeries.ts)
    )
    return list(session.scalars(stmt))


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


def _history_bounds(data_dir: str) -> tuple[date, date]:
    """Span of the historical precio_bolsa year CSVs under `data_dir`."""
    try:
        names = get_storage(data_dir).list_dir("precio_bolsa")
    except OSError as exc:
        raise ValueError(
            f"no se pudo listar {data_dir}/precio_bolsa para el backfill ({exc})"
        ) from exc
    years = sorted(
        int(name[len("precio_bolsa_") : -4])
        for name in names
        if name.startswith("precio_bolsa_") and name.endswith(".csv")
    )
    if not years:
        raise ValueError(
            f"no hay CSVs historicos precio_bolsa_*.csv bajo {data_dir}/precio_bolsa; "
            "pase --start/--end explicitos"
        )
    return date(years[0], 1, 1), date(years[-1], 12, 31)


def backfill_externals(
    session: Session,
    *,
    data_dir: str = "data",
    start: date | None = None,
    end: date | None = None,
) -> int:
    """REQ-HS-06: replay external hourly rows from the historical CSVs.

    With no explicit bounds the full span of the historical year CSVs is
    replayed. Idempotent: re-running upserts the same rows in place.
    """
    if start is None or end is None:
        lo, hi = _history_bounds(data_dir)
        start = start or lo
        end = end or hi
    return ingest_external_window(session, start=start, end_day=end, data_dir=data_dir)


def backfill_run_rows(session: Session) -> int:
    """REQ-HS-06: replay hourly rows of every done run (covers runs finished
    before the finish-time writer existed). Same helper -> idempotent."""
    runs = list(session.scalars(select(Run).where(Run.status == "done")))
    total = 0
    for run in runs:
        total += ingest_run_price_rows(session, run)
    return total


def main(argv: Sequence[str] | None = None) -> int:
    """One-time `hourly_series` backfill entrypoint (`python -m app.db.series`)."""
    parser = argparse.ArgumentParser(
        prog="python -m app.db.series",
        description=(
            "Backfill hourly_series from the historical CSVs and done runs "
            "(REQ-HS-06). Idempotent; safe to re-run."
        ),
    )
    parser.add_argument("--data-dir", default="data")
    parser.add_argument(
        "--start",
        type=date.fromisoformat,
        help="first Bogota day to replay (default: span of the year CSVs)",
    )
    parser.add_argument(
        "--end",
        type=date.fromisoformat,
        help="last Bogota day to replay (default: span of the year CSVs)",
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL"),
        help="SQLAlchemy URL (default: $DATABASE_URL)",
    )
    args = parser.parse_args(argv)
    if not args.database_url:
        parser.error("DATABASE_URL is not set and --database-url was not passed")
    engine = get_engine(args.database_url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        external = backfill_externals(
            session, data_dir=args.data_dir, start=args.start, end=args.end
        )
        run_rows = backfill_run_rows(session)
    print(f"hourly_series backfill ok: {external} external rows, {run_rows} run rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
