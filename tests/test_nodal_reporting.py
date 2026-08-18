import json
import math

from app.nodal.engine.egret_engine import EgretNodalEngine
from app.nodal.reporting import save_nodal_artifacts
from app.nodal.settlement.compare import compare_settlements
from app.nodal.settlement.lmp import settle_lmp
from app.nodal.settlement.status_quo import settle_status_quo
from tests.fixtures.nodal import make_three_zone_network


def _run(out_dir: str):
    net = make_three_zone_network(congested=True)
    sol = EgretNodalEngine().solve(net, use_unit_commitment=False)
    a = settle_status_quo(sol)
    b = settle_lmp(sol)
    c = compare_settlements(a, b, sol)
    return save_nodal_artifacts(sol, a, b, c, out_dir=out_dir)


def test_artifacts_written(tmp_path):
    paths = _run(str(tmp_path))
    names = (
        "lmp",
        "dispatch",
        "branch_flows",
        "settlement_status_quo",
        "settlement_lmp",
        "comparison",
        "summary.json",
    )
    for name in names:
        assert name in paths, f"missing artifact {name}"
        assert tmp_path.joinpath(paths[name].split("/")[-1]).exists() or paths[name].startswith(
            str(tmp_path)
        )

    with open(tmp_path.joinpath(paths["summary.json"].split("/")[-1])) as f:
        summary = json.load(f)
    assert math.isclose(summary["metrics"]["congestion_rent_total"], 24 * 7200, abs_tol=1e-3)
    assert summary["totals"]["total_load_payment_b"] > summary["totals"]["total_load_payment_a"]
