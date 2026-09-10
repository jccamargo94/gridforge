"""SCN-HS-06 backfill against the xm_smoke fixture.

A one-time replay of the historical CSVs (plus done runs) must leave every
(series, day) with its 24 rows in the correct COP/MWh unit, and re-running
it must change nothing (idempotent — no duplicates, no holes).
"""

from datetime import date
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session

from app.db import queries, series
from app.db.models import Base, HourlySeries
from app.schemas import DispatchCase, DispatchLevel, RunResult

FECHA = date(2024, 4, 18)
DD = str(Path(__file__).parent / "fixtures" / "xm_smoke")


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _counts(session):
    rows = list(session.scalars(select(HourlySeries)).all())
    counts = {}
    for r in rows:
        counts[r.series_key] = counts.get(r.series_key, 0) + 1
    return counts


def test_backfill_writes_24_rows_per_series_in_correct_unit():
    """SCN-HS-06-01: bolsa raw 200 COP/kWh -> 200000.0 COP/MWh; mpo 150000.0."""
    session = _session()
    written = series.backfill_externals(session, data_dir=DD, start=FECHA, end=FECHA)
    assert written == 48

    counts = _counts(session)
    assert counts == {"bolsa_tx1": 24, "mpo_xm": 24}

    rows = list(session.scalars(select(HourlySeries)).all())
    assert {r.value for r in rows if r.series_key == "bolsa_tx1"} == {200000.0}
    assert {r.value for r in rows if r.series_key == "mpo_xm"} == {150000.0}
    assert all(r.tenant_id is None for r in rows)


def test_backfill_rerun_is_idempotent():
    """SCN-HS-06-02: re-running over the same range changes nothing."""
    session = _session()
    assert series.backfill_externals(session, data_dir=DD, start=FECHA, end=FECHA) == 48
    assert series.backfill_externals(session, data_dir=DD, start=FECHA, end=FECHA) == 48
    counts = _counts(session)
    assert counts == {"bolsa_tx1": 24, "mpo_xm": 24}


def test_backfill_replays_done_run_rows(tmp_path):
    """Done runs finished before the hourly writer existed are replayed by
    the backfill through the same upsert path (idempotent)."""
    session = _session()
    run = queries.create_case_and_run(
        session,
        dispatch_date=FECHA,
        level="preideal",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
        user_id=None,
        visibility="public",
    )
    path = tmp_path / "price.csv"
    hours = pd.date_range("2024-04-18", periods=24, freq="h")
    pd.DataFrame({"datetime": hours, "ideal_marginal_price": [3000.0] * 24}).to_csv(
        path, index=False
    )
    queries.finish_run_ok(
        session,
        run,
        RunResult(
            case=DispatchCase(dispatch_date=FECHA, level=DispatchLevel.preideal),
            ok=True,
            price_path=str(path),
        ),
        out_dir=str(tmp_path),
    )
    # simulate the pre-change state: rows written at finish are wiped out
    session.execute(delete(HourlySeries))
    session.commit()
    assert _counts(session) == {}

    written = series.backfill_run_rows(session)
    assert written == 24
    counts = _counts(session)
    assert counts == {"ideal_marginal_price": 24}

    # replay again -> idempotent
    assert series.backfill_run_rows(session) == 24
    assert _counts(session) == {"ideal_marginal_price": 24}
