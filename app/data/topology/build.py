# app/data/topology/build.py
from __future__ import annotations

import math

from app.data.topology.units import reactance_pu
from app.nodal.network.schemas import (
    Branch,
    Generator,
    NodalNetwork,
    Zone,
)


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    if None in (lat1, lon1, lat2, lon2):
        return float("inf")
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _nearest_zone(lat, lon, subs, subarea=None) -> str:
    pool = [s for s in subs if subarea is None or s["subarea"] == subarea]
    if not pool:
        pool = subs  # fall back to global nearest
    best = min(pool, key=lambda s: _haversine_km(lat, lon, s["latitude"], s["longitude"]))
    return best["name"]


def assign_generators(gens: list[dict], subs: list[dict]) -> list[Generator]:
    out = []
    for g in gens:
        zone = _nearest_zone(g["latitude"], g["longitude"], subs, g["subarea"])
        out.append(
            Generator(
                name=g["name"],
                zone=zone,
                p_max=g["capacity"],
                marginal_cost=g["marginal_cost"],
                fuel=g["fuel"],
            )
        )
    return out


def build_demand_shares(
    subs: list[dict],
    generators: list[Generator],
    demand: dict[str, list[float]],
    split: str,
) -> dict[str, float]:
    # Total daily energy per subarea.
    subarea_total = {name: sum(vals) for name, vals in demand.items()}
    # Capacity per zone (from the already-assigned generators).
    zone_cap: dict[str, float] = {s["name"]: 0.0 for s in subs}
    for g in generators:
        zone_cap[g.zone] = zone_cap.get(g.zone, 0.0) + g.p_max

    shares: dict[str, float] = {s["name"]: 0.0 for s in subs}
    for s in subs:
        subarea = s["subarea"]
        if subarea not in subarea_total or subarea_total[subarea] <= 0:
            continue
        members = [x for x in subs if x["subarea"] == subarea]
        if split == "uniform":
            weight = 1.0 / len(members) if members else 0.0
        else:  # capacity
            total_cap = sum(zone_cap[x["name"]] for x in members)
            if total_cap > 0:
                weight = zone_cap[s["name"]] / total_cap
            else:
                weight = 1.0 / len(members) if members else 0.0
        shares[s["name"]] += subarea_total[subarea] * weight

    total = sum(shares.values())
    if total <= 0:
        raise ValueError("demand produced zero total energy; check demand source/date")
    return {z: v / total for z, v in shares.items()}


def build_network(
    subs: list[dict],
    lines: list[dict],
    gens: list[dict],
    demand: dict[str, list[float]],
    *,
    demand_split: str = "capacity",
    reference_zone: str | None = None,
) -> NodalNetwork:
    zones = [Zone(name=s["name"], base_kv=s["base_kv"]) for s in subs]
    generators = assign_generators(gens, subs)
    branches = [
        Branch(
            name=line["name"],
            from_zone=line["from_zone"],
            to_zone=line["to_zone"],
            reactance=reactance_pu(line["reactance_ohm"], line["kv"]),
            rating=line["rating"],
        )
        for line in lines
    ]
    demand_shares = build_demand_shares(subs, generators, demand, demand_split)
    ref = reference_zone or zones[0].name
    # NodalNetwork validator raises ValueError naming dangling refs / bad shares.
    return NodalNetwork(
        reference_zone=ref,
        zones=zones,
        generators=generators,
        branches=branches,
        demand_shares=demand_shares,
    )
