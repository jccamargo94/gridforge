import json
from pathlib import Path

import pytest

from app.data.topology import build, parse

FIX = Path(__file__).parent / "fixtures" / "topology"


def _load(name):
    return json.loads((FIX / f"{name}.json").read_text())


def test_golden_fixtures_build_valid_network():
    raw = {
        name: _load(name)
        for name in ("substations", "lines", "capacity", "thermal_fuel", "hydro", "solar", "wind")
    }
    subs = parse.parse_substations(raw["substations"])
    lines = parse.parse_lines(raw["lines"])
    gens = parse.parse_generators(
        raw["capacity"], raw["thermal_fuel"], raw["hydro"], raw["solar"], raw["wind"]
    )
    demand = parse.parse_demand((FIX / "ddem.txt").read_text(), "ddem")
    network = build.build_network(subs, lines, gens, demand)
    assert [z.name for z in network.zones] == ["AGUABLANCA", "ALFEREZ II"]
    assert len(network.generators) == 1
    assert len(network.branches) == 1


@pytest.mark.live
def test_live_fetch_paratec(tmp_path):
    from app.data.topology import fetch
    from app.storage import LocalStorage

    storage = LocalStorage(str(tmp_path))
    raw = fetch.fetch_all(storage)
    assert "data" in raw["substations"]
