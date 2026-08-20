from app.data.topology.units import reactance_pu


def test_reactance_pu_formula():
    assert reactance_pu(66.125, 115.0) == 66.125 * 100.0 / (115.0**2)


def test_reactance_pu_zero_kv_returns_zero():
    assert reactance_pu(10.0, 0.0) == 0.0
