from datetime import date
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import queries
from app.db.models import Base
from app.scheduler.reeval import (
    REEVAL_REFERENCE,
    REEVAL_SOURCE_KIND,
    reevaluate_metrics,
)
from app.schemas import DispatchCase, DispatchLevel, RunResult

FECHA = date(2024, 4, 18)
DD = str(Path(__file__).parent / "fixtures" / "xm_smoke")


def _imar_text(mpo: float) -> str:
    row = ",".join([f"{mpo:.2f}"] * 24)
    return "\n".join(
        [
            f'"Costo Marginal",{row}',
            f'"Delta",{",".join(["0.00"] * 24)}',
            f'"MPO",{row}',
        ]
    )


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _done_run(session, tmp_path, level=DispatchLevel.preideal):
    run = queries.create_case_and_run(
        session,
        dispatch_date=FECHA,
        level=level.value,
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
    )
    out = tmp_path / "results" / run.id
    out.mkdir(parents=True)
    hours = pd.date_range("2024-04-18", periods=24, freq="h")
    pd.DataFrame({"datetime": hours, "ideal_marginal_price": [180000.0] * 24}).to_csv(
        out / "price.csv", index=False
    )
    result = RunResult(
        case=DispatchCase(dispatch_date=FECHA, level=level),
        ok=True,
        price_path=str(out / "price.csv"),
        metrics={"mae": 30000.0},
    )
    queries.finish_run_ok(session, run, result, out_dir=str(out))
    return run


def test_reeval_metadata_maps():
    assert REEVAL_SOURCE_KIND == {
        "reeval_preideal": "preideal_daily",
        "reeval_ideal": "ideal_daily",
    }
    assert REEVAL_REFERENCE == {"reeval_preideal": "iMAR", "reeval_ideal": "bolsa_tx1"}


def test_reevaluate_metrics_against_imar_stamps_reference(tmp_path, monkeypatch):
    session = _session()
    run = _done_run(session, tmp_path)
    refreshed = []
    monkeypatch.setattr(
        "app.data.download.force_refresh_blob", lambda *a, **kw: refreshed.append(a)
    )
    metrics = reevaluate_metrics(session, run, reference="iMAR", data_dir=DD)
    assert metrics["mae"] == 30000.0  # 180000 model vs 150000 iMAR fixture
    ms = queries.get_metric_set(session, run.id)
    assert ms.reference == "iMAR"
    assert ms.evaluated_at is not None
    assert ms.mae == 30000.0
    assert ms.rmse == 30000.0
    assert refreshed == [("iMAR", FECHA, DD)]


def test_reevaluate_imar_metrics_use_force_refreshed_blob(tmp_path, monkeypatch):
    """Post-final-review: the iMAR blob is re-downloaded before evaluating, so
    the metrics always reflect the FINAL post-modification file. A preliminary
    local copy (MPO 100000) must be ignored once the refresh brings the final
    one (MPO 150000): model 180000 vs 100000 would give mae 80000."""
    session = _session()
    run = _done_run(session, tmp_path)
    data_dir = str(tmp_path / "livedata")
    flat = Path(data_dir) / "2024-04-18"
    flat.mkdir(parents=True)
    (flat / "iMAR0418.txt").write_text(_imar_text(100_000.0))
    refreshed = []

    def _fake_refresh(file_type, file_date, data_dir="data"):
        refreshed.append((file_type, file_date, data_dir))
        Path(data_dir, str(file_date), "iMAR0418.txt").write_text(_imar_text(150_000.0))

    monkeypatch.setattr("app.data.download.force_refresh_blob", _fake_refresh)
    metrics = reevaluate_metrics(session, run, reference="iMAR", data_dir=data_dir)
    assert refreshed == [("iMAR", FECHA, data_dir)]
    assert metrics["mae"] == 30000.0  # 180000 model vs refreshed 150000
    ms = queries.get_metric_set(session, run.id)
    assert ms.reference == "iMAR"
    assert ms.mae == 30000.0


def test_reevaluate_metrics_against_bolsa_stamps_reference(tmp_path):
    session = _session()
    run = _done_run(session, tmp_path, level=DispatchLevel.ideal)
    metrics = reevaluate_metrics(session, run, reference="bolsa_tx1", data_dir=DD)
    # fixture precio_bolsa raw COP/kWh = 200 -> loader scales x1e3 -> 200000.0
    assert metrics["mae"] == 20000.0
    ms = queries.get_metric_set(session, run.id)
    assert ms.reference == "bolsa_tx1"


def test_reevaluate_metrics_raises_when_price_csv_missing(tmp_path):
    session = _session()
    run = queries.create_case_and_run(
        session,
        dispatch_date=FECHA,
        level="preideal",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
    )
    try:
        reevaluate_metrics(session, run, reference="iMAR", data_dir=DD)
        assert False, "expected an exception"
    except ValueError as exc:
        assert "precio" in str(exc)
