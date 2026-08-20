from app.data.topology.builders import subarea

SUBS = [
    {
        "name": "A1",
        "base_kv": 230.0,
        "subarea": "SubArea Valle",
        "latitude": 3.4,
        "longitude": -76.5,
    },
    {
        "name": "A2",
        "base_kv": 115.0,
        "subarea": "SubArea Valle",
        "latitude": 3.5,
        "longitude": -76.5,
    },
    {
        "name": "B1",
        "base_kv": 230.0,
        "subarea": "SubArea Bogota",
        "latitude": 4.6,
        "longitude": -74.1,
    },
]
# A2 - GHOST_TAP and FOO - BAR are Line/getAll-only entries not present in the
# map endpoint (map coverage gap): GHOST_TAP/FOO/BAR are not substations, they
# simulate a generator-tap spur and a fully-unresolved line respectively.
LINES = [
    {
        "name": "A1 - B1 1",
        "from_zone": "A1",
        "to_zone": "B1",
        "reactance_ohm": 50.0,
        "kv": 230.0,
        "rating": 100.0,
        "subarea": "SubArea Valle",
    },
    {
        "name": "A1 - A2 1",
        "from_zone": "A1",
        "to_zone": "A2",
        "reactance_ohm": 20.0,
        "kv": 115.0,
        "rating": 80.0,
        "subarea": "SubArea Valle",
    },
    {
        "name": "A2 - GHOST_TAP 1",
        "from_zone": "A2",
        "to_zone": "GHOST_TAP",
        "reactance_ohm": 30.0,
        "kv": 115.0,
        "rating": 40.0,
        "subarea": "SubArea Valle",
    },
    {
        "name": "FOO - BAR 1",
        "from_zone": "FOO",
        "to_zone": "BAR",
        "reactance_ohm": 10.0,
        "kv": 115.0,
        "rating": 20.0,
        "subarea": "SubArea Valle",
    },
]
# Only the first two lines are in the map (by name) — the other two exercise
# the Line/getAll gap-fill path.
MAP_LINES = [
    {"name": "A1 - B1 1", "sub1": "A1", "sub2": "B1"},
    {"name": "A1 - A2 1", "sub1": "A1", "sub2": "A2"},
]
GENS = [
    {
        "name": "G1",
        "capacity": 50.0,
        "fuel": "hydro",
        "marginal_cost": 0.0,
        "subarea": "SubArea Valle",
        "latitude": None,
        "longitude": None,
    },
]
DEMAND = {
    "SubArea Valle": [100.0] * 24,
    "SubArea Bogota": [300.0] * 24,
}


def test_combine_parallel_two_identical_lines_halves_reactance():
    x_total, rating_total = subarea._combine_parallel([(0.1, 50.0), (0.1, 50.0)])
    assert rating_total == 100.0
    assert abs(x_total - 0.05) < 1e-12


def test_build_subarea_network_zones_from_substation_subarea():
    network, _ = subarea.build_subarea_network(SUBS, LINES, GENS, DEMAND, map_lines=MAP_LINES)
    assert {z.name for z in network.zones} == {"SubArea Valle", "SubArea Bogota"}
    assert network.reference_zone in {"SubArea Valle", "SubArea Bogota"}


def test_build_subarea_network_inter_zone_branch_from_map_endpoint():
    network, _ = subarea.build_subarea_network(SUBS, LINES, GENS, DEMAND, map_lines=MAP_LINES)
    assert len(network.branches) == 1
    branch = network.branches[0]
    assert {branch.from_zone, branch.to_zone} == {"SubArea Valle", "SubArea Bogota"}
    assert branch.rating == 100.0


def test_build_subarea_network_fuses_intra_zone_and_gap_lines():
    # A1-A2 (intra, via map), A2-GHOST_TAP (intra via gap-fill,
    # one side unresolved), FOO-BAR (intra via gap-fill, both sides unresolved,
    # falls back to the line's own `subarea` field) — all three fuse into
    # "SubArea Valle", none becomes a Branch.
    _, intra_summary = subarea.build_subarea_network(SUBS, LINES, GENS, DEMAND, map_lines=MAP_LINES)
    assert intra_summary["SubArea Valle"]["n_lines"] == 3
    assert intra_summary["SubArea Valle"]["rating_mw"] == 140.0
    assert "SubArea Bogota" not in intra_summary


def test_build_subarea_network_generator_zone_is_its_own_subarea():
    network, _ = subarea.build_subarea_network(SUBS, LINES, GENS, DEMAND, map_lines=MAP_LINES)
    gen = network.generators[0]
    assert gen.zone == "SubArea Valle"
    assert gen.p_max == 50.0


def test_build_subarea_network_demand_shares_sum_to_one():
    network, _ = subarea.build_subarea_network(SUBS, LINES, GENS, DEMAND, map_lines=MAP_LINES)
    assert set(network.demand_shares) == {"SubArea Valle", "SubArea Bogota"}
    assert abs(network.demand_shares["SubArea Valle"] - 0.25) < 1e-9
    assert abs(network.demand_shares["SubArea Bogota"] - 0.75) < 1e-9
    assert abs(sum(network.demand_shares.values()) - 1.0) < 1e-9
