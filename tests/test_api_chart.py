from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from app.db import queries, series
from app.schemas import DispatchCase, DispatchLevel, RunResult
from services.api import chart

FECHA = date(2024, 4, 18)
DD = str(Path(__file__).parent / "fixtures" / "xm_smoke")
START = FECHA - timedelta(days=29)


def _finish_public_run(api_client, tmp_path, *, level, grade, price):
    session = api_client.SessionLocal()
    run = queries.create_case_and_run(
        session,
        dispatch_date=FECHA,
        level=level,
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
        user_id=None,
        visibility="public",
        input_grade=grade,
    )
    out = tmp_path / "results" / run.id
    out.mkdir(parents=True)
    hours = pd.date_range("2024-04-18", periods=24, freq="h")
    pd.DataFrame({"datetime": hours, "ideal_marginal_price": [price] * 24}).to_csv(
        out / "price.csv", index=False
    )
    result = RunResult(
        case=DispatchCase(dispatch_date=FECHA, level=DispatchLevel(level)),
        ok=True,
        price_path=str(out / "price.csv"),
    )
    queries.finish_run_ok(session, run, result, out_dir=str(out))
    run_id = run.id  # refresh post-commit while the session is still open
    session.close()
    return run_id


def _seed_externals(session):
    """Seed the fixture's external rows into hourly_series (backfill-style):
    bolsa raw 200 COP/kWh -> 200000.0 COP/MWh, iMAR MPO -> 150000.0."""
    series.ingest_external_window(session, start=FECHA, end_day=FECHA, data_dir=DD)


def _rows(api_client, tmp_path, *, days=30):
    session = api_client.SessionLocal()
    _seed_externals(session)
    rows = chart.build_chart_series(session, days=days, today=FECHA, user_id="user-1")
    session.close()
    return {r["date"]: r for r in rows}


def test_preideal_falls_back_to_provisional_when_no_settled(api_client, tmp_path):
    prov_run = _finish_public_run(
        api_client, tmp_path, level="preideal", grade="provisional", price=3000.0
    )
    by_day = _rows(api_client, tmp_path, days=30)
    row = by_day["2024-04-18"]
    assert row["preideal"] == 3000.0
    assert row["preideal_run_id"] == prov_run
    assert row["preideal_hourly"] == [3000.0] * 24
    assert row["ideal_settled"] is None
    assert row["ideal_provisional"] is None


def test_preideal_settled_wins_over_provisional(api_client, tmp_path):
    _finish_public_run(api_client, tmp_path, level="preideal", grade="provisional", price=3000.0)
    settled_run = _finish_public_run(
        api_client, tmp_path, level="preideal", grade="settled", price=1000.0
    )
    row = _rows(api_client, tmp_path, days=30)["2024-04-18"]
    assert row["preideal"] == 1000.0
    assert row["preideal_run_id"] == settled_run
    assert row["preideal_hourly"] == [1000.0] * 24


def test_ideal_lanes_are_reported_separately(api_client, tmp_path):
    settled = _finish_public_run(api_client, tmp_path, level="ideal", grade="settled", price=1000.0)
    prov = _finish_public_run(
        api_client, tmp_path, level="ideal", grade="provisional", price=2000.0
    )
    row = _rows(api_client, tmp_path, days=30)["2024-04-18"]
    assert row["ideal_settled"] == 1000.0
    assert row["ideal_settled_run_id"] == settled
    assert row["ideal_settled_hourly"] == [1000.0] * 24
    assert row["ideal_provisional"] == 2000.0
    assert row["ideal_provisional_run_id"] == prov
    assert row["ideal_provisional_hourly"] == [2000.0] * 24


def test_external_series_from_seeded_hourly_rows(api_client, tmp_path):
    # no simulated runs needed: bolsa (raw 200 * 1e3) and mpo (iMAR 150000)
    row = _rows(api_client, tmp_path, days=30)["2024-04-18"]
    # goldens unchanged vs the old CSV-serving path (SCN-HC-01-01: the daily
    # value equals the mean of the 24 hourly rows it is derived from)
    assert row["bolsa_tx1"] == 200000.0
    assert row["mpo_xm"] == 150000.0
    assert row["bolsa_tx1_hourly"] == [200000.0] * 24
    assert row["mpo_xm_hourly"] == [150000.0] * 24
    assert row["bolsa_tx1"] == sum(row["bolsa_tx1_hourly"]) / 24
    assert row["mpo_xm"] == sum(row["mpo_xm_hourly"]) / 24
    assert row["preideal"] is None
    assert row["preideal_hourly"] == [None] * 24


def test_gap_day_without_rows_serves_null_not_zero(api_client, tmp_path):
    """SCN-HC-01-02: a day with no hourly rows stays null (never 0)."""
    row = _rows(api_client, tmp_path, days=30)[START.isoformat()]
    assert row["bolsa_tx1"] is None
    assert row["bolsa_tx1_hourly"] == [None] * 24
    assert row["mpo_xm"] is None
    assert row["preideal"] is None
    assert row["preideal_run_id"] is None


def test_series_endpoint_shape_and_days_bounds(api_client, tmp_path):
    resp = api_client.get("/chart/series?days=30")
    assert resp.status_code == 200
    rows = resp.json()
    assert isinstance(rows, list)
    assert set(rows[0]) == {
        "date",
        "bolsa_tx1",
        "mpo_xm",
        "ideal_settled",
        "ideal_settled_run_id",
        "ideal_provisional",
        "ideal_provisional_run_id",
        "preideal",
        "preideal_run_id",
        "bolsa_tx1_hourly",
        "mpo_xm_hourly",
        "ideal_settled_hourly",
        "ideal_provisional_hourly",
        "preideal_hourly",
    }
    assert len(rows) <= 30
    for r in rows:
        assert len(r["bolsa_tx1_hourly"]) == 24
        assert len(r["mpo_xm_hourly"]) == 24
        assert len(r["preideal_hourly"]) == 24
    assert api_client.get("/chart/series?days=0").status_code == 422
    assert api_client.get("/chart/series?days=91").status_code == 422
