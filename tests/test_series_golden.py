"""SCN-HS-04 golden scale pins for the hourly_series writers.

End-to-end pins over the xm_smoke fixture: whatever pipeline path writes a
series — external backfill replay (bolsa raw 200 COP/kWh -> 200000.0 COP/MWh,
iMAR MPO 150000.0 COP/MWh) or run closure (price CSV 3000 COP/MWh ->
3000.0) — the stored values must be COP/MWh. If a raw-scale value (class
1000x) ever lands in the table, the pin guard fails (SCN-HS-04-02).
"""

from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import queries, series
from app.db.models import Base, HourlySeries
from app.schemas import DispatchCase, DispatchLevel, RunResult

UTC = timezone.utc
FECHA = date(2024, 4, 18)
DD = str(Path(__file__).parent / "fixtures" / "xm_smoke")

# per-series COP/MWh pinned scale for the fixture (B4)
PINNED = {
    "bolsa_tx1": 200000.0,  # raw 200 COP/kWh x1e3
    "mpo_xm": 150000.0,  # iMAR MPO, already COP/MWh
    "ideal_marginal_price": 3000.0,  # run price CSV, already COP/MWh
}


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _assert_scale_pins(session):
    """Golden guard: every stored value must match its pinned COP/MWh scale."""
    rows = list(session.scalars(select(HourlySeries)).all())
    assert len(rows) == 72  # 24 bolsa + 24 mpo + 24 run
    by_key = {key: {r.value for r in rows if r.series_key == key} for key in PINNED}
    assert by_key == {key: {expected} for key, expected in PINNED.items()}


def test_golden_external_scale_from_backfill():
    session = _session()
    written = series.backfill_externals(session, data_dir=DD, start=FECHA, end=FECHA)
    assert written == 48

    rows = list(session.scalars(select(HourlySeries)).all())
    bolsa = [r for r in rows if r.series_key == "bolsa_tx1"]
    mpo = [r for r in rows if r.series_key == "mpo_xm"]
    # SCN-HS-04-01: stored value is COP/MWh (x1e3), never the raw COP/kWh 200.0
    assert len(bolsa) == 24 and {r.value for r in bolsa} == {200000.0}
    assert len(mpo) == 24 and {r.value for r in mpo} == {150000.0}
    assert all(r.tenant_id is None for r in rows)


def test_golden_run_scale_from_finish(tmp_path):
    session = _session()
    run = queries.create_case_and_run(
        session,
        dispatch_date=FECHA,
        level="ideal",
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
    result = RunResult(
        case=DispatchCase(dispatch_date=FECHA, level=DispatchLevel.ideal),
        ok=True,
        price_path=str(path),
    )
    queries.finish_run_ok(session, run, result, out_dir=str(tmp_path))

    rows = list(session.scalars(select(HourlySeries)).all())
    assert len(rows) == 24
    assert {r.value for r in rows} == {3000.0}  # run CSV is already COP/MWh


def test_golden_full_pipeline_pins_and_raw_scale_detection(tmp_path):
    """SCN-HS-04-02: after the full fixture pipeline the pin guard holds, and
    it fires the moment a raw-scale row (as a naive writer would persist)
    enters the table."""
    session = _session()
    series.backfill_externals(session, data_dir=DD, start=FECHA, end=FECHA)
    run = queries.create_case_and_run(
        session,
        dispatch_date=FECHA,
        level="ideal",
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
            case=DispatchCase(dispatch_date=FECHA, level=DispatchLevel.ideal),
            ok=True,
            price_path=str(path),
        ),
        out_dir=str(tmp_path),
    )
    _assert_scale_pins(session)

    # simulate the 1000x bug: a naive writer persisting the raw bolsa scale
    # on a day that has no rows yet (a fresh insert never hits the dedupe)
    session.add(
        HourlySeries(
            ts=datetime(2024, 4, 19, 5, 0, tzinfo=UTC),
            tenant_id=None,
            series_key="bolsa_tx1",
            value=200.0,  # raw COP/kWh — must never be stored
            source="xm",
        )
    )
    session.commit()
    with pytest.raises(AssertionError):
        _assert_scale_pins(session)
