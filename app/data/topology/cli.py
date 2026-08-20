from __future__ import annotations

import json
from datetime import datetime

import typer

from app.data.topology import fetch, parse
from app.data.topology.builders import BUILDERS
from app.storage import get_storage


def scrape_topology_cmd(
    d: str = typer.Option(..., "--date", help="Case date (YYYY-MM-DD)."),
    demand_source: str = typer.Option("ddem", "--demand-source"),
    demand_split: str = typer.Option("capacity", "--demand-split"),
    scope: str = typer.Option("subarea", "--scope", help="subarea|node|area"),
    out: str = typer.Option("topology/network.json", "--out"),
    refresh: bool = typer.Option(False, "--refresh"),
    data_dir: str = typer.Option("data", "--data-dir"),
) -> None:
    """Build a NodalNetwork topology from PARATEC data for a given date."""
    if demand_source not in ("ddem", "pron"):
        raise typer.BadParameter(f"must be 'ddem' or 'pron', got {demand_source!r}")
    if scope not in BUILDERS:
        raise typer.BadParameter(f"scope must be one of {sorted(BUILDERS)}, got {scope!r}")
    dispatch_date = datetime.strptime(d, "%Y-%m-%d").date()
    storage = get_storage(data_dir)
    raw = fetch.fetch_all(storage, refresh=refresh)
    demand_text = fetch.fetch_demand(storage, dispatch_date, demand_source)

    subs = parse.parse_substations(raw["substations"])
    lines = parse.parse_lines(raw["lines"])
    map_lines = parse.parse_map_lines(raw["lines_map"])
    gens = parse.parse_generators(
        raw["capacity"],
        raw["thermal_fuel"],
        raw["hydro"],
        raw["solar"],
        raw["wind"],
    )
    demand = parse.parse_demand(demand_text, demand_source)

    builder = BUILDERS[scope]
    network, extra = builder(
        subs, lines, gens, demand, map_lines=map_lines, demand_split=demand_split
    )

    with storage.open(out, "w") as fh:
        json.dump(network.model_dump(), fh, indent=2, ensure_ascii=False)

    extra_msg = ""
    if extra:
        summary_path = "topology/network_summary.json"
        with storage.open(summary_path, "w") as fh:
            json.dump(extra, fh, indent=2, ensure_ascii=False)
        extra_msg = f" Intra-zone summary written to {summary_path}."

    typer.echo(
        f"Topology written to {out} (scope={scope}): {len(network.zones)} zones, "
        f"{len(network.generators)} generators, {len(network.branches)} branches."
        f"{extra_msg}"
    )
