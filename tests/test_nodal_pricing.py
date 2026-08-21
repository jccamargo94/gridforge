import math

from app.nodal.engine.pricing import congestion_component, demand_weighted_average_price


def test_demand_weighted_average_equal_loads_is_simple_average():
    lmp = {"norte": [20.0], "centro": [80.0], "sur": [80.0]}
    loads = {"norte": [100.0], "centro": [100.0], "sur": [100.0]}
    avg = demand_weighted_average_price(lmp, loads, ["norte", "centro", "sur"], 1)
    assert math.isclose(avg[0], 60.0, abs_tol=1e-9)


def test_demand_weighted_average_weights_by_load():
    lmp = {"norte": [20.0], "centro": [80.0]}
    loads = {"norte": [300.0], "centro": [100.0]}
    avg = demand_weighted_average_price(lmp, loads, ["norte", "centro"], 1)
    # (20*300 + 80*100) / 400 = 35.0
    assert math.isclose(avg[0], 35.0, abs_tol=1e-9)


def test_congestion_component_identity_and_zero_sum():
    lmp = {"norte": [20.0], "centro": [80.0], "sur": [80.0]}
    loads = {"norte": [100.0], "centro": [100.0], "sur": [100.0]}
    avg = demand_weighted_average_price(lmp, loads, ["norte", "centro", "sur"], 1)
    congestion = congestion_component(lmp, avg, ["norte", "centro", "sur"], 1)
    assert math.isclose(congestion["norte"][0], -40.0, abs_tol=1e-9)
    assert math.isclose(congestion["centro"][0], 20.0, abs_tol=1e-9)
    assert math.isclose(congestion["sur"][0], 20.0, abs_tol=1e-9)
    # load-weighted congestion sums to zero -- pure redistribution
    weighted_sum = sum(loads[b][0] * congestion[b][0] for b in ("norte", "centro", "sur"))
    assert math.isclose(weighted_sum, 0.0, abs_tol=1e-6)
    # identity: lmp == avg + congestion, per bus
    for b in ("norte", "centro", "sur"):
        assert math.isclose(lmp[b][0], avg[0] + congestion[b][0], abs_tol=1e-9)
