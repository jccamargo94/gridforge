"""Hourly series ingest helpers (D2 shared upsert, REQ-HS-01/02, B3).

SCN-HS-01-02: re-writing the same public key updates the value without a
duplicate row. D2: public and tenant rows resolve different conflict targets.
B3: ingest helpers never raise on missing/unreadable sources — they log and
skip (hours stay absent = gap, never zero).
"""

from datetime import date, datetime, time, timezone

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db import series
from app.db.models import Base, HourlySeries, Tenant

UTC = timezone.utc
FECHA = date(2024, 4, 18)


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _public_batch(day=FECHA, value=200000.0, series_key="bolsa_tx1", source="xm"):
    rows = []
    for hour in range(24):
        rows.append(
            HourlySeries(
                ts=datetime.combine(day, time(hour), tzinfo=UTC),
                tenant_id=None,
                series_key=series_key,
                value=value,
                source=source,
            )
        )
    return rows


def _count(session):
    return session.scalar(select(func.count()).select_from(HourlySeries))


def test_upsert_hourly_rows_public_key_updates_in_place():
    session = _session()
    rows = _public_batch(value=200000.0)

    assert series.upsert_hourly_rows(session, rows) == 24
    assert _count(session) == 24

    # SCN-HS-01-02: re-writing the same keys updates, never duplicates
    replayed = _public_batch(value=999999.0)
    assert series.upsert_hourly_rows(session, replayed) == 24
    assert _count(session) == 24

    values = {r.value for r in session.scalars(select(HourlySeries)).all()}
    assert values == {999999.0}
    assert {r.tenant_id for r in session.scalars(select(HourlySeries)).all()} == {None}


def test_upsert_hourly_rows_tenant_and_public_rows_have_own_conflict_targets():
    session = _session()
    tenant = Tenant(name="acme-energia")
    session.add(tenant)
    session.commit()

    public = _public_batch(value=200000.0)
    scoped = [
        HourlySeries(
            ts=r.ts, tenant_id=tenant.id, series_key=r.series_key, value=r.value, source=r.source
        )
        for r in public
    ]
    assert series.upsert_hourly_rows(session, [*public, *scoped]) == 48
    assert _count(session) == 48

    # tenant re-write updates only the tenant copy; public copy untouched
    replay = [
        HourlySeries(
            ts=r.ts, tenant_id=tenant.id, series_key=r.series_key, value=777.0, source=r.source
        )
        for r in public
    ]
    assert series.upsert_hourly_rows(session, replay) == 24
    assert _count(session) == 48

    pairs = {(r.tenant_id, r.value) for r in session.scalars(select(HourlySeries)).all()}
    assert pairs == {(None, 200000.0), (tenant.id, 777.0)}


def test_ingest_external_window_missing_sources_skip_without_raise(tmp_path, caplog):
    """B3: no year CSV and no iMAR blob -> zero rows written, no exception."""
    session = _session()
    with caplog.at_level("WARNING", logger="app.db.series"):
        written = series.ingest_external_window(
            session, start=FECHA, end_day=FECHA, data_dir=str(tmp_path)
        )
    assert written == 0
    assert _count(session) == 0
    assert any("bolsa_tx1" in r.message or "precio_bolsa" in r.message for r in caplog.records)
