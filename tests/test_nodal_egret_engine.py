import math

from app.nodal.engine.base import NodalSolution
from app.nodal.engine.egret_engine import EgretNodalEngine
from tests.fixtures.nodal import make_three_zone_network


def _hour0(sol: NodalSolution) -> int:
    return 0


def test_uncongested_pure_dcopf():
    sol = EgretNodalEngine().solve(
        make_three_zone_network(congested=False), use_unit_commitment=False
    )
    assert sol.reference_zone == "norte"
    for bus in sol.buses:
        assert math.isclose(sol.lmp[bus][0], 20.0, abs_tol=1e-6)
    assert math.isclose(sol.dispatch["G_N"][0], 300.0, abs_tol=1e-6)
    assert math.isclose(sol.dispatch["G_C"][0], 0.0, abs_tol=1e-6)
    assert math.isclose(sol.total_cost, 144000.0, rel_tol=1e-6)
    assert sol.uc_total_cost is None


def test_congested_pure_dcopf_lmps():
    sol = EgretNodalEngine().solve(
        make_three_zone_network(congested=True), use_unit_commitment=False
    )
    assert math.isclose(sol.lmp["norte"][0], 20.0, abs_tol=1e-6)
    assert math.isclose(sol.lmp["centro"][0], 80.0, abs_tol=1e-6)
    assert math.isclose(sol.lmp["sur"][0], 80.0, abs_tol=1e-6)
    assert math.isclose(sol.dispatch["G_N"][0], 220.0, abs_tol=1e-6)
    assert math.isclose(sol.dispatch["G_C"][0], 80.0, abs_tol=1e-6)
    assert math.isclose(sol.dispatch["G_S"][0], 0.0, abs_tol=1e-6)
    assert math.isclose(sol.total_cost, 259200.0, rel_tol=1e-6)
    assert math.isclose(sol.branch_flows["NC"][0], 120.0, abs_tol=1e-6)


def test_uc_path_matches_dcopf_on_constant_loads():
    for congested in (False, True):
        sol = EgretNodalEngine().solve(
            make_three_zone_network(congested=congested), use_unit_commitment=True
        )
        assert all(v in (0.0, 1.0) for g in sol.commitment for v in sol.commitment[g])
        assert sol.uc_total_cost is not None and sol.uc_total_cost > 0
        assert math.isclose(sol.total_cost, sol.uc_total_cost, rel_tol=1e-6)
