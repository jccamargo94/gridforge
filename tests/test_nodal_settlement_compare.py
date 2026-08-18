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
    # Loads pay more under LMP in this congested fixture (totals over 24h).
    # north pays 2000 vs 4400 (delta -2400), centro 8000 vs 4400 (+3600), sur 8000 vs 4400 (+3600).
    assert math.isclose(c.metrics["load_payment_delta"], 115200.0, abs_tol=1e-4)
    # Redistribution matrix
    red = c.redistribution.set_index("zone")
    assert math.isclose(red.loc["norte", "delta"], -57600.0, abs_tol=1e-4)
    assert math.isclose(red.loc["centro", "delta"], 86400.0, abs_tol=1e-4)
    assert math.isclose(red.loc["sur", "delta"], 86400.0, abs_tol=1e-4)
    # Generator revenue moves to congested-area generators
    assert math.isclose(c.metrics["gen_revenue_delta"], 115200.0, abs_tol=1e-4)
    # Congestion rent invariant
    assert math.isclose(c.metrics["congestion_rent_total"], 24 * 7200, abs_tol=1e-3)
    # Zone price stats present
    assert "price_avg_norte" in c.metrics and "price_vol_norte" in c.metrics
