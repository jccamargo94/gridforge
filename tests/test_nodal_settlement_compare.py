import math

from app.nodal.engine.egret_engine import EgretNodalEngine
from app.nodal.settlement.compare import compare_settlements
from app.nodal.settlement.lmp import settle_lmp
from app.nodal.settlement.status_quo import settle_status_quo
from tests.fixtures.nodal import make_three_zone_network


def test_compare_congested_hour_zero():
    sol = EgretNodalEngine().solve(
        make_three_zone_network(congested=True), use_unit_commitment=False
    )
    a = settle_status_quo(sol)
    b = settle_lmp(sol)
    c = compare_settlements(a, b, sol)

    # Total production cost is identical in both regimes (same dispatch).
    assert math.isclose(c.metrics["total_cost"], 259200.0, rel_tol=1e-6)
    # Loads pay more under status_quo now (weighted-average energy price 60 vs zone LMP).
    # delta = total_load_payment_b - total_load_payment_a = 432000 - 604800 = -172800.
    assert math.isclose(c.metrics["load_payment_delta"], -172800.0, abs_tol=1e-4)
    # Redistribution matrix
    red = c.redistribution.set_index("zone")
    assert math.isclose(red.loc["norte", "delta"], -153600.0, abs_tol=1e-4)
    assert math.isclose(red.loc["centro", "delta"], -9600.0, abs_tol=1e-4)
    assert math.isclose(red.loc["sur", "delta"], -9600.0, abs_tol=1e-4)
    # Generator revenue mirrors load payment: same total delta
    assert math.isclose(c.metrics["gen_revenue_delta"], -172800.0, abs_tol=1e-4)
    # Congestion rent invariant
    assert math.isclose(c.metrics["congestion_rent_total"], 24 * 7200, abs_tol=1e-3)
    # Zone price stats present
    assert "price_avg_norte" in c.metrics and "price_vol_norte" in c.metrics
