import tempfile

from app.nodal.network.schemas import Branch, BusLoad, Generator, NodalNetwork, Zone
from app.nodal.network.to_egret import (
    enforce_commitment,
    model_data_for_hour,
    nodal_to_model_data,
)

TIME_KEYS = [f"H{h:02d}" for h in range(24)]


def _net() -> NodalNetwork:
    return NodalNetwork(
        reference_zone="norte",
        zones=[Zone(name="norte"), Zone(name="centro")],
        generators=[
            Generator(name="G1", zone="norte", p_min=10.0, p_max=100.0, marginal_cost=20.0),
            Generator(name="G2", zone="centro", p_max=50.0, marginal_cost=80.0),
        ],
        branches=[
            Branch(name="NC", from_zone="norte", to_zone="centro", reactance=0.1, rating=100.0)
        ],
        loads=[
            BusLoad(zone="norte", p_load=[10.0] * 24),
            BusLoad(zone="centro", p_load=[10.0] * 24),
        ],
    )


def test_model_data_structure():
    md = nodal_to_model_data(_net(), TIME_KEYS)
    buses = dict(md.elements("bus"))
    gens = dict(md.elements("generator"))
    branches = dict(md.elements("branch"))
    loads = dict(md.elements("load"))
    assert set(buses) == {"norte", "centro"}
    assert set(gens) == {"G1", "G2"}
    assert set(branches) == {"NC"}
    assert set(loads) == {"norte", "centro"}
    g1 = gens["G1"]
    assert g1["bus"] == "norte"
    assert g1["p_min"] == 10.0 and g1["p_max"] == 100.0
    assert g1["p_cost"]["cost_curve_type"] == "polynomial"
    assert g1["p_cost"]["values"][1] == 20.0
    assert g1["initial_status"] in (1, -1)
    assert g1["startup_cost"][0][0] == g1["min_down_time"]
    assert "angle_diff_min" in branches["NC"] and "angle_diff_max" in branches["NC"]
    assert md.data["system"]["baseMVA"] == 100.0
    assert md.data["system"]["reference_bus"] == "norte"
    assert loads["norte"]["p_load"]["values"] == [10.0] * 24


def test_hour_clone_collapses_time_series():
    md = nodal_to_model_data(_net(), TIME_KEYS)
    hour = model_data_for_hour(md, "H00")
    load = dict(hour.elements("load"))["norte"]["p_load"]
    assert load == 10.0
    assert hour.data["system"]["time_keys"] == TIME_KEYS


def test_enforce_commitment_zeroes_offline_gens():
    md = nodal_to_model_data(_net(), TIME_KEYS)
    hour = model_data_for_hour(md, "H00")
    enforce_commitment(_net(), hour, {"G1": 1.0, "G2": 0.0}, 0)
    gens = dict(hour.elements("generator"))
    assert gens["G1"]["p_min"] == 10.0 and gens["G1"]["p_max"] == 100.0
    assert gens["G2"]["p_min"] == 0.0 and gens["G2"]["p_max"] == 0.0


def test_model_data_round_trip_json():
    md = nodal_to_model_data(_net(), TIME_KEYS)
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        md.write(f.name)
        restored = type(md).read(f.name)
    assert sorted(dict(restored.elements("bus"))) == sorted(dict(md.elements("bus")))
