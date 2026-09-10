"""Hourly series ingest helpers (D2 shared upsert, REQ-HS-01/02/03, B3).

SCN-HS-01-02: re-writing the same public key updates the value without a
duplicate row. D2: public and tenant rows resolve different conflict targets.
REQ-HS-03/B1: closing a run upserts ideal_marginal_price rows under the run
id — public runs under tenant NULL, private runs under every tenant the
owner belongs to (zero memberships -> no rows at all, no public leak).
B3: ingest helpers never raise on missing/unreadable sources — they log and
skip (hours stay absent = gap, never zero).
"""

from datetime import date, datetime, time, timezone

import pandas as pd
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db import queries, series
from app.db.models import Base, HourlySeries, Tenant, TenantMember
from app.schemas import DispatchCase, DispatchLevel, RunResult

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


def _write_price_csv(tmp_path, *, value=3000.0, day=FECHA):
    path = tmp_path / "price.csv"
    hours = pd.date_range(f"{day.isoformat()}", periods=24, freq="h")
    pd.DataFrame({"datetime": hours, "ideal_marginal_price": [value] * 24}).to_csv(
        path, index=False
    )
    return str(path)


def _finish_run(
    session, tmp_path, *, user_id=None, visibility="public", price_value=3000.0, price_path=None
):
    run = queries.create_case_and_run(
        session,
        dispatch_date=FECHA,
        level="ideal",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
        user_id=user_id,
        visibility=visibility,
    )
    if price_path is None:
        price_path = _write_price_csv(tmp_path, value=price_value)
    case = DispatchCase(dispatch_date=FECHA, level=DispatchLevel.ideal)
    result = RunResult(case=case, ok=True, price_path=price_path)
    queries.finish_run_ok(session, run, result, out_dir=str(tmp_path))
    return run.id


def _stored(session):
    rows = list(session.scalars(select(HourlySeries)).all())
    return rows


def _add_membership(session, user_id, tenant_id):
    session.add(TenantMember(tenant_id=tenant_id, user_id=user_id))
    session.commit()


def test_finish_run_ok_public_run_writes_24_ideal_rows(tmp_path):
    """SCN-HS-03-01: done public run -> 24 ideal_marginal_price rows,
    tenant NULL, source = run id, COP/MWh value stored as-is (B4)."""
    session = _session()
    run_id = _finish_run(session, tmp_path, user_id=None, visibility="public", price_value=3000.0)

    rows = _stored(session)
    assert len(rows) == 24
    assert {r.tenant_id for r in rows} == {None}
    assert {r.series_key for r in rows} == {"ideal_marginal_price"}
    assert {r.source for r in rows} == {run_id}
    assert {r.value for r in rows} == {3000.0}


def test_finish_run_ok_private_owner_membership_rows_under_tenant(tmp_path):
    """REQ-HS-03/B1: private run whose owner belongs to one tenant -> every
    row under that tenant, none public."""
    session = _session()
    tenant = Tenant(name="acme-energia")
    session.add(tenant)
    session.commit()
    _add_membership(session, "user-1", tenant.id)

    run_id = _finish_run(session, tmp_path, user_id="user-1", visibility="private")

    rows = _stored(session)
    assert len(rows) == 24
    assert {r.tenant_id for r in rows} == {tenant.id}
    assert {r.source for r in rows} == {run_id}


def test_finish_run_ok_private_owner_multiple_tenants_writes_each(tmp_path):
    """B1 (supersedes D4): multi-tenant owner -> rows under EVERY member
    tenant, never public."""
    session = _session()
    t1 = Tenant(name="acme-energia")
    t2 = Tenant(name="zapata-sas")
    session.add_all([t1, t2])
    session.commit()
    _add_membership(session, "user-1", t1.id)
    _add_membership(session, "user-1", t2.id)

    run_id = _finish_run(session, tmp_path, user_id="user-1", visibility="private")

    rows = _stored(session)
    assert len(rows) == 48
    assert {r.tenant_id for r in rows} == {t1.id, t2.id}
    assert sum(1 for r in rows if r.tenant_id == t1.id) == 24
    assert sum(1 for r in rows if r.tenant_id == t2.id) == 24
    assert {r.source for r in rows} == {run_id}


def test_finish_run_ok_private_owner_without_membership_writes_nothing(tmp_path):
    """SCN-HS-03-02: private run whose owner belongs to no tenant -> no row
    at all, and none with tenant NULL (no public leak)."""
    session = _session()
    _finish_run(session, tmp_path, user_id="user-1", visibility="private")
    assert _stored(session) == []


def test_finish_run_ok_unreadable_price_path_never_raises(tmp_path):
    """B3: a missing price file must not fail the run closure — executor
    marks solved runs failed on any exception, so ingest must skip instead."""
    session = _session()
    run_id = _finish_run(
        session,
        tmp_path,
        user_id=None,
        visibility="public",
        price_path=str(tmp_path / "does-not-exist.csv"),
    )
    updated = queries.get_run(session, run_id)
    assert updated.status == "done"
    assert _stored(session) == []
