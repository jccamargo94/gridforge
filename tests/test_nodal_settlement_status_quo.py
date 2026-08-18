import math

from app.nodal.engine.egret_engine import EgretNodalEngine
from app.nodal.settlement.status_quo import settle_status_quo
from tests.fixtures.nodal import make_three_zone_network


def test_status_quo_uncongested():
    sol = EgretNodalEngine().solve(
        make_three_zone_network(congested=False), use_unit_commitment=False
    )
    s = settle_status_quo(sol)
    assert s.regime == "status_quo"
    assert all(math.isclose(p, 20.0) for p in s.energy_price)
    assert all(math.isclose(r, 0.0, abs_tol=1e-6) for r in s.congestion_rent)
    assert all(math.isclose(u, 0.0, abs_tol=1e-6) for u in s.uplift)
    assert math.isclose(s.total_load_payment, 24 * 300 * 20.0)
    assert math.isclose(s.total_gen_revenue, 24 * 300 * 20.0)


def test_status_quo_congested_hour_zero():
    sol = EgretNodalEngine().solve(
        make_three_zone_network(congested=True), use_unit_commitment=False
    )
    s = settle_status_quo(sol)
    t = 0
    assert math.isclose(s.energy_price[t], 20.0)
    assert math.isclose(s.congestion_rent[t], 7200.0, abs_tol=1e-4)
    assert math.isclose(s.uplift[t], 7200.0, abs_tol=1e-4)
    # uplift split by load share (100/300 each zone)
    assert math.isclose(s.zone_load_payment["norte"][t], 20 * 100 + 7200 * 100 / 300, abs_tol=1e-4)
    assert math.isclose(s.zone_load_payment["centro"][t], 20 * 100 + 7200 * 100 / 300, abs_tol=1e-4)
    # generation paid the single price
    assert math.isclose(s.gen_revenue["G_N"][t], 20 * 220, abs_tol=1e-4)
    assert math.isclose(s.gen_revenue["G_C"][t], 20 * 80, abs_tol=1e-4)
    # identity: load payments == gen revenue + congestion rent
    assert math.isclose(s.total_load_payment, s.total_gen_revenue + 24 * 7200, rel_tol=1e-6)
