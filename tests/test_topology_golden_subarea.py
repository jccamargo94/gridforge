import json
from pathlib import Path

import pytest

from app.data.topology import parse
from app.data.topology.builders.subarea import build_subarea_network

FIX = Path(__file__).parent / "fixtures" / "topology_subarea"


def _load(name):
    return json.loads((FIX / f"{name}.json").read_text())


def test_golden_fixtures_build_valid_subarea_network():
    raw = {
        name: _load(name)
        for name in (
            "substations",
            "lines",
            "lines_map",
            "capacity",
            "thermal_fuel",
            "hydro",
            "solar",
            "wind",
        )
    }
    subs = parse.parse_substations(raw["substations"])
    lines = parse.parse_lines(raw["lines"])
    map_lines = parse.parse_map_lines(raw["lines_map"])
    gens = parse.parse_generators(
        raw["capacity"], raw["thermal_fuel"], raw["hydro"], raw["solar"], raw["wind"]
    )
    demand = parse.parse_demand((FIX / "ddem.txt").read_text(), "ddem")
    network, intra_summary = build_subarea_network(subs, lines, gens, demand, map_lines=map_lines)

    assert {z.name for z in network.zones} == {"SubArea Valle", "SubArea Bogota"}
    assert len(network.branches) == 1
    branch = network.branches[0]
    assert {branch.from_zone, branch.to_zone} == {"SubArea Valle", "SubArea Bogota"}
    assert intra_summary["SubArea Valle"]["n_lines"] == 3
    assert abs(sum(network.demand_shares.values()) - 1.0) < 1e-9


@pytest.mark.live
def test_live_map_lines_are_covered_by_line_getall(tmp_path):
    """Regression guard for this plan's core empirical finding: every line
    name in TransmissionMap/getLines has an exact match in Line/getAll's
    name. If PARATEC breaks this, build_subarea_network silently drops the
    unmatched map lines instead of erroring — this test is what would catch
    that drift."""
    from app.data.topology import fetch
    from app.storage import LocalStorage

    storage = LocalStorage(str(tmp_path))
    raw = fetch.fetch_all(storage)
    lines = parse.parse_lines(raw["lines"])
    map_lines = parse.parse_map_lines(raw["lines_map"])
    line_names = {line["name"] for line in lines}
    unmatched = [ml["name"] for ml in map_lines if ml["name"] not in line_names]
    assert unmatched == []
