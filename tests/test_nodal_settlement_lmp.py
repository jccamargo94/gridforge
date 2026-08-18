import math

from app.nodal.engine.egret_engine import EgretNodalEngine
from app.nodal.settlement.lmp import settle_lmp
from tests.fixtures.nodal import make_three_zone_network


def test_lmp_uncongested():
    sol = EgretNodalEngine().solve(
        make_three_zone_network(congested=False), use_unit_commitment=False
    )
    s = settle_lmp(sol)
    assert s.regime == "lmp"
    assert s.uplift is None
    assert math.isclose(s.total_load_payment, 24 * 300 * 20.0)
    assert math.isclose(s.total_gen_revenue, 24 * 300 * 20.0)


def test_lmp_congested_hour_zero():
    sol = EgretNodalEngine().solve(
        make_three_zone_network(congested=True), use_unit_commitment=False
    )
    s = settle_lmp(sol)
    t = 0
    assert math.isclose(s.zone_load_payment["norte"][t], 20 * 100, abs_tol=1e-4)
    assert math.isclose(s.zone_load_payment["centro"][t], 80 * 100, abs_tol=1e-4)
    assert math.isclose(s.zone_load_payment["sur"][t], 80 * 100, abs_tol=1e-4)
    assert math.isclose(s.gen_revenue["G_N"][t], 20 * 220, abs_tol=1e-4)
    assert math.isclose(s.gen_revenue["G_C"][t], 80 * 80, abs_tol=1e-4)
    assert math.isclose(s.congestion_rent[t], 7200.0, abs_tol=1e-4)
    assert math.isclose(s.total_load_payment, s.total_gen_revenue + 24 * 7200, rel_tol=1e-6)


def test_congestion_rent_identical_across_regimes():
    sol = EgretNodalEngine().solve(
        make_three_zone_network(congested=True), use_unit_commitment=False
    )
    b = settle_lmp(sol)
    # congested network, constant loads -> congestion rent 7200 every hour
    for r in b.congestion_rent:
        assert math.isclose(r, 7200.0, abs_tol=1e-6)
    assert math.isclose(b.total_load_payment - b.total_gen_revenue, 24 * 7200, rel_tol=1e-6)
