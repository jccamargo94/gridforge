import json

from app.nodal.runner import run_nodal
from app.schemas import DispatchCase, DispatchLevel
from tests.fixtures.nodal import make_three_zone_network


def test_run_nodal_writes_artifacts(tmp_path):
    net = make_three_zone_network(congested=True)
    net_path = tmp_path / "net.json"
    net_path.write_text(json.dumps(net.model_dump()))
    case = DispatchCase(
        dispatch_date="2024-04-18", level=DispatchLevel.lmp, nodal_network=str(net_path)
    )
    result = run_nodal(case, out=str(tmp_path / "out"), data_dir=str(tmp_path))
    assert result.ok, result.error
    assert result.metrics["congestion_rent_total"] > 0
    assert tmp_path.joinpath("out", "2024-04-18-lmp", "summary.json").exists()


def test_run_nodal_populates_nodal_result_with_full_paths(tmp_path):
    net = make_three_zone_network(congested=True)
    net_path = tmp_path / "net.json"
    net_path.write_text(json.dumps(net.model_dump()))
    case = DispatchCase(
        dispatch_date="2024-04-18", level=DispatchLevel.lmp, nodal_network=str(net_path)
    )
    out_dir = str(tmp_path / "out")
    result = run_nodal(case, out=out_dir, data_dir=str(tmp_path))
    assert result.ok, result.error
    nodal = result.nodal
    assert nodal is not None
    # dispatch_path ya no es relativo (bug latente corregido)
    assert result.dispatch_path == f"{out_dir}/2024-04-18-lmp/dispatch.csv"
    assert nodal.lmp_path == f"{out_dir}/2024-04-18-lmp/lmp.csv"
    assert nodal.summary_path == f"{out_dir}/2024-04-18-lmp/summary.json"
    assert nodal.network["name"] == "three_zone"
    assert len(nodal.redistribution) == 3
    assert len(nodal.gen_revenue_by_zone) == 3
    for attr in (
        "lmp_path",
        "dispatch_path",
        "branch_flows_path",
        "settlement_status_quo_path",
        "settlement_lmp_path",
        "comparison_path",
        "summary_path",
    ):
        assert getattr(nodal, attr) is not None
