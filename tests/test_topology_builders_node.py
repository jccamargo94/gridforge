import pytest

from app.data.topology.builders import BUILDERS

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
        "subarea": "SubArea Valle",
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


def test_node_builder_registered_and_matches_build_network_directly():
    from app.data.topology.build import build_network

    network_direct = build_network(SUBS, LINES, GENS, DEMAND)
    network_via_registry, extra = BUILDERS["node"](SUBS, LINES, GENS, DEMAND, map_lines=[])

    assert network_via_registry.model_dump() == network_direct.model_dump()
    assert extra == {}


def test_area_builder_raises_not_implemented():
    with pytest.raises(NotImplementedError):
        BUILDERS["area"](SUBS, LINES, GENS, DEMAND, map_lines=[])
