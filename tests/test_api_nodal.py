from datetime import date

import pandas as pd

from app.db import queries
from app.schemas import DispatchCase, DispatchLevel, NodalRunResult, RunResult
from tests.fixtures.nodal import make_three_zone_network

ZONES = ["norte", "centro", "sur"]


def _seed_done_nodal_run(api_client, tmp_path):
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

    lmp_rows = [
        {"timestamp": f"2024-04-18 {h:02d}:00", "bus": z, "lmp": 20.0 + h}
        for h in range(24)
        for z in ZONES
    ]
    pd.DataFrame(lmp_rows).to_csv(out_dir / "lmp.csv", index=False)
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
            metrics={"total_cost": 100.0, "congestion_rent_total": 7200.0},
            redistribution=[{"zone": "norte", "delta": 1.0}],
            gen_revenue_by_zone=[{"zone": "norte", "fuel": "hydro", "delta": 2.0}],
            network={"name": "three_zone"},
        ),
    )
    queries.finish_nodal_run_ok(session, run, result, out_dir=str(run_out))
    session.close()
    return run_id


def test_create_nodal_run_with_network(api_client):
    resp = api_client.post(
        "/runs",
        json={
            "dispatch_date": "2024-04-18",
            "level": "lmp",
            "nodal_network": make_three_zone_network(congested=True).model_dump(),
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pending"
    run_id = body["run_id"]
    session = api_client.SessionLocal()
    run = queries.get_run(session, run_id)
    case = queries.get_case(session, run.case_id)
    assert case.nodal_network["name"] == "three_zone"
    session.close()


def test_create_run_rejects_nodal_network_for_non_lmp(api_client):
    resp = api_client.post(
        "/runs",
        json={
            "dispatch_date": "2024-04-18",
            "level": "preideal",
            "nodal_network": make_three_zone_network().model_dump(),
        },
    )
    assert resp.status_code == 400


def test_get_nodal_run_detail(api_client, tmp_path):
    run_id = _seed_done_nodal_run(api_client, tmp_path)
    resp = api_client.get(f"/runs/{run_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["metrics"] is None
    assert body["artifacts"] == {
        "dispatch": False,
        "prices": False,
        "bess": False,
        "marginal_plants": False,
    }
    nodal = body["nodal"]
    assert nodal["network"]["name"] == "three_zone"
    assert nodal["metrics"]["congestion_rent_total"] == 7200.0
    assert nodal["artifacts"] == {
        name: True
        for name in (
            "lmp",
            "dispatch",
            "branch_flows",
            "settlement_status_quo",
            "settlement_lmp",
            "comparison",
            "summary",
        )
    }


def test_get_nodal_artifact_lmp_returns_72_rows(api_client, tmp_path):
    run_id = _seed_done_nodal_run(api_client, tmp_path)
    resp = api_client.get(f"/runs/{run_id}/nodal/lmp")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 72
    assert rows[0]["bus"] == "norte"


def test_get_nodal_artifact_summary_returns_parsed_json(api_client, tmp_path):
    run_id = _seed_done_nodal_run(api_client, tmp_path)
    resp = api_client.get(f"/runs/{run_id}/nodal/summary")
    assert resp.status_code == 200
    assert resp.json()["metrics"]["total_cost"] == 100.0


def test_download_nodal_summary(api_client, tmp_path):
    run_id = _seed_done_nodal_run(api_client, tmp_path)
    resp = api_client.get(f"/runs/{run_id}/download/nodal/summary.json")
    assert resp.status_code == 200


def test_get_nodal_artifact_404_for_unknown_artifact(api_client, tmp_path):
    run_id = _seed_done_nodal_run(api_client, tmp_path)
    resp = api_client.get(f"/runs/{run_id}/nodal/not-a-real-artifact")
    assert resp.status_code == 404


def test_nodal_run_ownership_404(api_client, tmp_path):
    run_id = _seed_done_nodal_run(api_client, tmp_path)
    session = api_client.SessionLocal()
    run = queries.get_run(session, run_id)
    run.user_id = "user-2"
    session.commit()
    session.close()
    resp = api_client.get(f"/runs/{run_id}/nodal/lmp")
    assert resp.status_code == 404
