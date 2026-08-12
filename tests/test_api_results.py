from datetime import date

import pandas as pd

from app.db import queries
from app.schemas import DispatchCase, DispatchLevel, RunResult


def _seed_done_run_with_dispatch_csv(api_client, tmp_path):
    resp = api_client.post("/runs", json={"dispatch_date": "2024-04-18", "level": "preideal"})
    run_id = resp.json()["run_id"]

    out_dir = tmp_path / "results" / run_id
    out_dir.mkdir(parents=True)
    dispatch_csv = out_dir / "dispatch_by_gen-2024-04-18-preideal.csv"
    pd.DataFrame(
        [{"generador": "TERMO1", "datetime": "2024-04-18 00:00", "dispatch": 300.0}]
    ).to_csv(dispatch_csv, index=False)

    session = api_client.SessionLocal()
    run = queries.get_run(session, run_id)
    result = RunResult(
        case=DispatchCase(dispatch_date=date(2024, 4, 18), level=DispatchLevel.preideal),
        ok=True,
        dispatch_path=str(dispatch_csv),
    )
    queries.finish_run_ok(session, run, result, out_dir=str(out_dir))
    session.close()

    return run_id


def test_get_run_dispatch_returns_json_rows(api_client, tmp_path):
    run_id = _seed_done_run_with_dispatch_csv(api_client, tmp_path)

    resp = api_client.get(f"/runs/{run_id}/dispatch")
    assert resp.status_code == 200
    rows = resp.json()
    assert rows[0]["generador"] == "TERMO1"
    assert rows[0]["dispatch"] == 300.0


def test_download_run_dispatch_returns_csv_file(api_client, tmp_path):
    run_id = _seed_done_run_with_dispatch_csv(api_client, tmp_path)

    resp = api_client.get(f"/runs/{run_id}/download/dispatch")
    assert resp.status_code == 200
    assert "TERMO1" in resp.text


def test_get_run_artifact_404_when_run_has_no_artifact_yet(api_client):
    resp = api_client.post("/runs", json={"dispatch_date": "2024-04-18", "level": "preideal"})
    run_id = resp.json()["run_id"]

    resp = api_client.get(f"/runs/{run_id}/dispatch")
    assert resp.status_code == 404


def test_get_run_artifact_404_for_unknown_artifact_name(api_client, tmp_path):
    run_id = _seed_done_run_with_dispatch_csv(api_client, tmp_path)

    resp = api_client.get(f"/runs/{run_id}/not-a-real-artifact")
    assert resp.status_code == 404


def test_download_run_artifact_404_when_file_missing_on_disk(api_client, tmp_path):
    resp = api_client.post("/runs", json={"dispatch_date": "2024-04-18", "level": "preideal"})
    run_id = resp.json()["run_id"]

    out_dir = tmp_path / "results" / run_id
    out_dir.mkdir(parents=True)
    dispatch_csv = out_dir / "dispatch_by_gen-2024-04-18-preideal.csv"  # never written

    session = api_client.SessionLocal()
    run = queries.get_run(session, run_id)
    result = RunResult(
        case=DispatchCase(dispatch_date=date(2024, 4, 18), level=DispatchLevel.preideal),
        ok=True,
        dispatch_path=str(dispatch_csv),
    )
    queries.finish_run_ok(session, run, result, out_dir=str(out_dir))
    session.close()

    resp = api_client.get(f"/runs/{run_id}/download/dispatch")
    assert resp.status_code == 404


def test_get_run_includes_bess_metrics(api_client, tmp_path):
    from app.db.models import MetricSet

    resp = api_client.post("/runs", json={"dispatch_date": "2024-04-18", "level": "preideal"})
    run_id = resp.json()["run_id"]

    session = api_client.SessionLocal()
    session.add(
        MetricSet(
            run_id=run_id,
            rmse=1.0,
            bess_charge_mwh=12.5,
            bess_discharge_mwh=11.0,
            bess_avg_soc_mwh=5.5,
            bess_net_revenue=987.0,
        )
    )
    session.commit()
    session.close()

    resp = api_client.get(f"/runs/{run_id}")
    metrics = resp.json()["metrics"]
    assert metrics["bess_charge_mwh"] == 12.5
    assert metrics["bess_discharge_mwh"] == 11.0
    assert metrics["bess_avg_soc_mwh"] == 5.5
    assert metrics["bess_net_revenue"] == 987.0


def _seed_run_with_price_and_marginal(api_client, tmp_path, monkeypatch):
    resp = api_client.post("/runs", json={"dispatch_date": "2024-04-18", "level": "preideal"})
    run_id = resp.json()["run_id"]

    out_dir = tmp_path / "results" / run_id
    out_dir.mkdir(parents=True)

    price_csv = out_dir / "marginal_price-2024-04-18-preideal.csv"
    pd.DataFrame(
        {
            "datetime": pd.date_range("2024-04-18", periods=24, freq="1h").astype(str),
            "ideal_marginal_price": [float(i) for i in range(24)],
        }
    ).to_csv(price_csv, index=False)

    marginal_csv = out_dir / "marginal_plants-2024-04-18-preideal.csv"
    pd.DataFrame(
        [
            {
                "datetime": "2024-04-18 00:00",
                "generador": "TERMO1",
                "dispatch": 100.0,
                "pmax": 200.0,
                "is_marginal": True,
            }
        ]
    ).to_csv(marginal_csv, index=False)

    # The API hardcodes data_dir="data" for the XM price; stub it out so the
    # test doesn't depend on a real data/ tree on disk.
    monkeypatch.setattr(
        "services.api.main.load_reference_price",
        lambda dispatch_date, level, data_dir="data": [float(i) for i in range(24)],
    )

    session = api_client.SessionLocal()
    run = queries.get_run(session, run_id)
    result = RunResult(
        case=DispatchCase(dispatch_date=date(2024, 4, 18), level=DispatchLevel.preideal),
        ok=True,
        price_path=str(price_csv),
        marginal_plants_path=str(marginal_csv),
        metrics={"mae": 1.0, "dispatch_mae_mw": 12.5, "dispatch_rmse_mw": 15.0},
    )
    queries.finish_run_ok(session, run, result, out_dir=str(out_dir))
    session.close()

    return run_id


def test_get_run_detail_includes_price_series_and_dispatch_metrics(
    api_client, tmp_path, monkeypatch
):
    run_id = _seed_run_with_price_and_marginal(api_client, tmp_path, monkeypatch)

    resp = api_client.get(f"/runs/{run_id}")
    assert resp.status_code == 200
    body = resp.json()

    assert body["metrics"]["dispatch_mae_mw"] == 12.5
    assert body["metrics"]["dispatch_rmse_mw"] == 15.0
    assert body["artifacts"]["marginal_plants"] is True

    price_series = body["price_series"]
    assert len(price_series) == 24
    assert price_series[0] == {
        "datetime": "2024-04-18 00:00:00",
        "model_mpo": 0.0,
        "xm_mpo": 0.0,
    }
    assert price_series[23]["model_mpo"] == 23.0


def test_get_run_detail_price_series_null_when_no_price(api_client):
    resp = api_client.post("/runs", json={"dispatch_date": "2024-04-18", "level": "preideal"})
    run_id = resp.json()["run_id"]

    resp = api_client.get(f"/runs/{run_id}")
    assert resp.json()["price_series"] is None


def test_get_run_marginal_plants_returns_json_rows(api_client, tmp_path, monkeypatch):
    run_id = _seed_run_with_price_and_marginal(api_client, tmp_path, monkeypatch)

    resp = api_client.get(f"/runs/{run_id}/marginal_plants")
    assert resp.status_code == 200
    rows = resp.json()
    assert rows[0]["generador"] == "TERMO1"
    assert rows[0]["dispatch"] == 100.0
    assert rows[0]["is_marginal"]


def test_download_marginal_plants_returns_csv(api_client, tmp_path, monkeypatch):
    run_id = _seed_run_with_price_and_marginal(api_client, tmp_path, monkeypatch)

    resp = api_client.get(f"/runs/{run_id}/download/marginal_plants")
    assert resp.status_code == 200
    assert "TERMO1" in resp.text


def test_download_price_comparison_returns_csv(api_client, tmp_path, monkeypatch):
    run_id = _seed_run_with_price_and_marginal(api_client, tmp_path, monkeypatch)

    resp = api_client.get(f"/runs/{run_id}/download/price_comparison")
    assert resp.status_code == 200
    assert "datetime,model_mpo,xm_mpo" in resp.text
    assert "2024-04-18" in resp.text


def test_download_price_comparison_404_when_no_price(api_client):
    resp = api_client.post("/runs", json={"dispatch_date": "2024-04-18", "level": "preideal"})
    run_id = resp.json()["run_id"]

    resp = api_client.get(f"/runs/{run_id}/download/price_comparison")
    assert resp.status_code == 404
