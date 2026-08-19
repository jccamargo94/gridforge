from datetime import date

import pandas as pd

from app.db import queries
from app.schemas import DispatchCase, DispatchLevel, NodalRunResult, RunResult
from tests.fixtures.nodal import make_three_zone_network


def test_create_run_returns_pending_status(api_client):
    resp = api_client.post("/runs", json={"dispatch_date": "2024-04-18", "level": "preideal"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pending"
    assert "run_id" in body


def test_create_run_rejects_unknown_scenario_id(api_client):
    resp = api_client.post(
        "/runs",
        json={"dispatch_date": "2024-04-18", "level": "preideal", "scenario_id": "missing"},
    )
    assert resp.status_code == 404


def test_get_run_returns_404_for_unknown_id(api_client):
    resp = api_client.get("/runs/does-not-exist")
    assert resp.status_code == 404


def test_get_run_returns_status_and_null_metrics_before_worker_runs(api_client):
    create_resp = api_client.post(
        "/runs", json={"dispatch_date": "2024-04-18", "level": "preideal"}
    )
    run_id = create_resp.json()["run_id"]

    resp = api_client.get(f"/runs/{run_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == run_id
    assert body["status"] == "pending"
    assert body["metrics"] is None


def test_get_run_returns_404_for_another_users_run(api_client):
    from datetime import date

    from app.db import queries

    session = api_client.SessionLocal()
    run = queries.create_case_and_run(
        session,
        dispatch_date=date(2024, 4, 18),
        level="preideal",
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
        user_id="user-2",
    )
    run_id = run.id
    session.close()

    resp = api_client.get(f"/runs/{run_id}")
    assert resp.status_code == 404


def test_list_runs_returns_created_runs(api_client):
    api_client.post("/runs", json={"dispatch_date": "2024-04-18", "level": "preideal"})
    api_client.post("/runs", json={"dispatch_date": "2024-04-19", "level": "ideal"})
    resp = api_client.get("/runs")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_get_run_includes_case_fields(api_client):
    create_resp = api_client.post(
        "/runs", json={"dispatch_date": "2024-04-18", "level": "preideal"}
    )
    run_id = create_resp.json()["run_id"]

    resp = api_client.get(f"/runs/{run_id}")
    body = resp.json()
    assert body["dispatch_date"] == "2024-04-18"
    assert body["level"] == "preideal"
    assert body["scenario_id"] is None


def test_list_runs_includes_case_fields(api_client):
    api_client.post("/runs", json={"dispatch_date": "2024-04-19", "level": "ideal"})
    resp = api_client.get("/runs")
    row = resp.json()[0]
    assert row["dispatch_date"] == "2024-04-19"
    assert row["level"] == "ideal"


def test_get_run_artifacts_all_false_before_worker_runs(api_client):
    resp = api_client.post("/runs", json={"dispatch_date": "2024-04-18", "level": "preideal"})
    run_id = resp.json()["run_id"]

    resp = api_client.get(f"/runs/{run_id}")
    assert resp.status_code == 200
    assert resp.json()["artifacts"] == {
        "dispatch": False,
        "prices": False,
        "bess": False,
        "marginal_plants": False,
    }


def test_get_run_artifacts_reflects_available_paths(api_client, tmp_path):
    from datetime import date

    from app.db import queries
    from app.schemas import DispatchCase, DispatchLevel, RunResult

    resp = api_client.post("/runs", json={"dispatch_date": "2024-04-18", "level": "preideal"})
    run_id = resp.json()["run_id"]

    out_dir = tmp_path / "results" / run_id
    out_dir.mkdir(parents=True)

    session = api_client.SessionLocal()
    run = queries.get_run(session, run_id)
    result = RunResult(
        case=DispatchCase(dispatch_date=date(2024, 4, 18), level=DispatchLevel.preideal),
        ok=True,
        dispatch_path=str(out_dir / "dispatch.csv"),
        price_path=str(out_dir / "price.csv"),
    )
    queries.finish_run_ok(session, run, result, out_dir=str(out_dir))
    session.close()

    resp = api_client.get(f"/runs/{run_id}")
    assert resp.json()["artifacts"] == {
        "dispatch": True,
        "prices": True,
        "bess": False,
        "marginal_plants": False,
    }


def _seed_done_nodal_run_with_network(api_client, tmp_path):
    resp = api_client.post(
        "/runs",
        json={
            "dispatch_date": "2024-04-18",
            "level": "lmp",
            "nodal_network": make_three_zone_network(congested=True).model_dump(),
        },
    )
    run_id = resp.json()["run_id"]

    run_out = tmp_path / "results" / run_id
    out_dir = run_out / "2024-04-18-lmp"
    out_dir.mkdir(parents=True)
    pd.DataFrame([{"timestamp": "2024-04-18 00:00", "bus": "norte", "lmp": 20.0}]).to_csv(
        out_dir / "lmp.csv", index=False
    )
    pd.DataFrame(
        [{"generator": "G_N", "zone": "norte", "fuel": "hydro", "hour": 0, "dispatch_mw": 100.0}]
    ).to_csv(out_dir / "dispatch.csv", index=False)
    pd.DataFrame([{"timestamp": "2024-04-18 00:00", "branch": "NC", "flow_mw": 10.0}]).to_csv(
        out_dir / "branch_flows.csv", index=False
    )
    pd.DataFrame(
        [{"zone": "norte", "hour": 0, "load_payment": 1.0, "gen_revenue": 1.0, "uplift": 0.0}]
    ).to_csv(out_dir / "settlement_status_quo.csv", index=False)
    pd.DataFrame([{"zone": "norte", "hour": 0, "load_payment": 1.0, "gen_revenue": 1.0}]).to_csv(
        out_dir / "settlement_lmp.csv", index=False
    )
    pd.DataFrame(
        [{"zone": "norte", "load_payment_a": 1.0, "load_payment_b": 2.0, "delta": 1.0}]
    ).to_csv(out_dir / "comparison.csv", index=False)
    (out_dir / "summary.json").write_text('{"metrics": {"total_cost": 100.0}}')

    session = api_client.SessionLocal()
    run = queries.get_run(session, run_id)
    case = DispatchCase(dispatch_date=date(2024, 4, 18), level=DispatchLevel.lmp)
    result = RunResult(
        case=case,
        ok=True,
        nodal=NodalRunResult(
            lmp_path=str(out_dir / "lmp.csv"),
            dispatch_path=str(out_dir / "dispatch.csv"),
            branch_flows_path=str(out_dir / "branch_flows.csv"),
            settlement_status_quo_path=str(out_dir / "settlement_status_quo.csv"),
            settlement_lmp_path=str(out_dir / "settlement_lmp.csv"),
            comparison_path=str(out_dir / "comparison.csv"),
            summary_path=str(out_dir / "summary.json"),
            metrics={"total_cost": 100.0},
            redistribution=[{"zone": "norte", "delta": 1.0}],
            gen_revenue_by_zone=[{"zone": "norte", "fuel": "hydro", "delta": 2.0}],
            network={
                "name": "three_zone",
                "zones": [
                    {"name": "norte", "base_kv": 230.0},
                    {"name": "centro", "base_kv": 230.0},
                    {"name": "sur", "base_kv": 230.0},
                ],
                "generators": [
                    {"name": "G_N", "zone": "norte"},
                    {"name": "G_C", "zone": "centro"},
                    {"name": "G_S", "zone": "sur"},
                ],
                "branches": [
                    {"name": "NC", "from_zone": "norte", "to_zone": "centro"},
                    {"name": "CS", "from_zone": "centro", "to_zone": "sur"},
                ],
            },
        ),
    )
    queries.finish_nodal_run_ok(session, run, result, out_dir=str(run_out))
    session.close()
    return run_id


def test_list_runs_includes_nodal_summary_for_nodal_run(api_client, tmp_path):
    run_id = _seed_done_nodal_run_with_network(api_client, tmp_path)
    resp = api_client.get("/runs")
    assert resp.status_code == 200
    runs = resp.json()
    nodal_run = next(r for r in runs if r["run_id"] == run_id)
    assert nodal_run["nodal"] == {
        "network_name": "three_zone",
        "zones": 3,
        "generators": 3,
        "branches": 2,
    }


def test_list_runs_returns_nodal_null_for_classic_run(api_client):
    resp = api_client.post("/runs", json={"dispatch_date": "2024-04-18", "level": "preideal"})
    assert resp.status_code == 200
    run_id = resp.json()["run_id"]
    resp = api_client.get("/runs")
    assert resp.status_code == 200
    runs = resp.json()
    classic_run = next(r for r in runs if r["run_id"] == run_id)
    assert classic_run["nodal"] is None
