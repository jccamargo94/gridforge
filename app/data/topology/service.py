from __future__ import annotations

from datetime import date
from typing import Any

import httpx

from app.data.topology import fetch, parse
from app.data.topology.builders import BUILDERS
from app.nodal.network.schemas import NodalNetwork
from app.storage import Storage


def scrape_topology(
    storage: Storage,
    dispatch_date: date,
    *,
    demand_source: str = "ddem",
    demand_split: str = "capacity",
    scope: str = "subarea",
    refresh: bool = False,
) -> tuple[NodalNetwork, dict[str, Any]]:
    """Fetch PARATEC + XM demand data and build a NodalNetwork for dispatch_date.

    Shared by the CLI (`scrape-topology`) and the API's scrape-trigger endpoint.
    """
    raw = fetch.fetch_all(storage, refresh=refresh)
    demand_text = fetch.fetch_demand(storage, dispatch_date, demand_source)

    subs = parse.parse_substations(raw["substations"])
    lines = parse.parse_lines(raw["lines"])
    map_lines = parse.parse_map_lines(raw["lines_map"])
    gens = parse.parse_generators(
        raw["capacity"], raw["thermal_fuel"], raw["hydro"], raw["solar"], raw["wind"]
    )
    demand = parse.parse_demand(demand_text, demand_source)

    builder = BUILDERS[scope]
    return builder(subs, lines, gens, demand, map_lines=map_lines, demand_split=demand_split)


def recompute_demand_shares(
    storage: Storage, dispatch_date: date, zone_names: list[str]
) -> tuple[dict[str, float], str]:
    """Recompute demand_shares for zone_names against dispatch_date's real demand.

    XM publishes dDEM (historical) with a lag, so a recent-past date may not
    have it yet: try the date-implied source first (ddem for today/past, pron
    for future) and fall back to the other on fetch failure. Returns the
    shares dict plus which source was actually used.
    """
    preferred = "ddem" if dispatch_date <= date.today() else "pron"
    fallback = "pron" if preferred == "ddem" else "ddem"
    for source in (preferred, fallback):
        try:
            demand_text = fetch.fetch_demand(storage, dispatch_date, source)
        except httpx.HTTPStatusError:
            continue
        demand = parse.parse_demand(demand_text, source)
        totals = {zone: sum(demand.get(zone, [])) for zone in zone_names}
        total = sum(totals.values())
        if total <= 0:
            continue
        return {zone: value / total for zone, value in totals.items()}, source
    raise ValueError(
        f"no demand data available for {dispatch_date} (tried {preferred}, {fallback})"
    )
