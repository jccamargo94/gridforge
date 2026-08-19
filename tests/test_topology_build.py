# tests/test_topology_build.py
import pytest

from app.data.topology import build

SUBS = [
    {
        "name": "CALI",
        "base_kv": 115.0,
        "subarea": "SubArea Valle",
        "latitude": 3.4,
        "longitude": -76.5,
    },
    {
        "name": "YUMBO",
        "base_kv": 115.0,
        "subarea": "SubArea Valle",
        "latitude": 3.5,
        "longitude": -76.5,
    },
]
LINES = [
    {
        "name": "CALI - YUMBO 1",
        "from_zone": "CALI",
        "to_zone": "YUMBO",
        "reactance_ohm": 66.125,
        "kv": 115.0,
        "rating": 120.0,
    },
]
GENS = [
    {
        "name": "H_CALI",
        "capacity": 200.0,
        "fuel": "hydro",
        "marginal_cost": 0.0,
        "subarea": "SubArea Valle",
        "latitude": 3.41,
        "longitude": -76.49,
    },
]
DEMAND = {"SubArea Valle": [100.0] * 24}


def test_build_network_assigns_generator_to_subarea_zone():
    network = build.build_network(SUBS, LINES, GENS, DEMAND)
    gen = next(g for g in network.generators if g.name == "H_CALI")
    # both zones are in SubArea Valle; nearest by coords → CALI
    assert gen.zone == "CALI"
    assert gen.p_max == 200.0


def test_demand_shares_cover_all_zones_and_sum_to_one():
    network = build.build_network(SUBS, LINES, GENS, DEMAND)
    assert set(network.demand_shares) == {"CALI", "YUMBO"}
    assert abs(sum(network.demand_shares.values()) - 1.0) < 1e-6


def test_build_fails_on_dangling_branch_zone():
    bad_lines = [
        {
            "name": "CALI - GHOST",
            "from_zone": "CALI",
            "to_zone": "GHOST",
            "reactance_ohm": 66.125,
            "kv": 115.0,
            "rating": 120.0,
        },
    ]
    with pytest.raises(ValueError, match="GHOST"):
        build.build_network(SUBS, bad_lines, GENS, DEMAND)


def test_build_converts_reactance_to_per_unit():
    network = build.build_network(SUBS, LINES, GENS, DEMAND)
    branch = network.branches[0]
    # X_pu = X_ohm × baseMVA / kV² = 66.125 × 100 / 115² = 0.5
    assert abs(branch.reactance - 0.5) < 1e-9
