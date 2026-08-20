from __future__ import annotations

from app.data.topology.units import reactance_pu
from app.nodal.network.schemas import Branch, Generator, NodalNetwork, Zone

# Border/frontier subareas — never populated by real domestic substations
# (verified live against PARATEC), but excluded explicitly and defensively
# in case that ever changes. See the design spec §3.4.
EXCLUDED_SUBAREAS = {
    "",
    "SubArea Ecuador138",
    "SubArea Ecuador230",
    "SubArea Venezuela_Corozo",
    "SubArea Venezuela_Cuatricentenario",
}


def _combine_parallel(entries: list[tuple[float, float]]) -> tuple[float, float]:
    """Combine (reactance_pu, rating) pairs of parallel lines into one.

    rating: capacities in parallel add. reactance: per-unit impedances in
    parallel combine as 1/X_total = Σ(1/X_i) — the standard electrical
    parallel-combination formula. Entries with zero reactance are dropped
    from the harmonic sum to avoid a division by zero (not expected in real
    PARATEC data, a defensive bookkeeping edge case only).
    """
    total_rating = sum(rating for _, rating in entries)
    inv_sum = sum(1.0 / x for x, _ in entries if x > 0)
    total_reactance = 1.0 / inv_sum if inv_sum > 0 else 0.0
    return total_reactance, total_rating


def _classify_and_collect(
    map_lines: list[dict],
    lines: list[dict],
    sub_to_subarea: dict[str, str],
) -> tuple[dict[frozenset[str], list[tuple[float, float]]], dict[str, list[tuple[float, float]]]]:
    """Split every line into an inter-subarea branch candidate or intra-subarea fusion.

    Primary source: map_lines (TransmissionMap/getLines) — sub1/sub2 are exact
    substation names, resolved via sub_to_subarea, electrical parameters
    cross-referenced from `lines` (parse_lines output) by exact line name.

    Gap-fill: any line present in `lines` but absent from `map_lines` (by
    name) is classified via its own from_zone/to_zone (the parse_lines
    subStation split). If neither endpoint resolves to a known substation,
    fall back to the line's own `subarea` field (always present on
    Line/getAll rows) — this can only ever produce an intra-zone fusion,
    never a cross-zone branch, since there is only one subarea to anchor it
    to.

    Returns (inter, intra):
      inter: {frozenset({subarea_a, subarea_b}): [(reactance_pu, rating), ...]}
      intra: {subarea: [(reactance_pu, rating), ...]}
    """
    line_by_name = {line["name"]: line for line in lines}
    inter: dict[frozenset[str], list[tuple[float, float]]] = {}
    intra: dict[str, list[tuple[float, float]]] = {}
    seen_names: set[str] = set()

    for ml in map_lines:
        matched = line_by_name.get(ml["name"])
        if matched is None:
            continue  # map line with no Line/getAll electrical record — skip
        seen_names.add(ml["name"])
        subarea_a = sub_to_subarea.get(ml["sub1"], "")
        subarea_b = sub_to_subarea.get(ml["sub2"], "")
        entry = (
            reactance_pu(matched["reactance_ohm"], matched["kv"]),
            matched["rating"],
        )
        if subarea_a and subarea_b and subarea_a != subarea_b:
            inter.setdefault(frozenset({subarea_a, subarea_b}), []).append(entry)
        else:
            zone = subarea_a or subarea_b
            if zone:
                intra.setdefault(zone, []).append(entry)

    for line in lines:
        if line["name"] in seen_names:
            continue
        subarea_a = sub_to_subarea.get(line["from_zone"], "")
        subarea_b = sub_to_subarea.get(line["to_zone"], "")
        entry = (
            reactance_pu(line["reactance_ohm"], line["kv"]),
            line["rating"],
        )
        if subarea_a and subarea_b and subarea_a != subarea_b:
            inter.setdefault(frozenset({subarea_a, subarea_b}), []).append(entry)
        else:
            zone = subarea_a or subarea_b or line["subarea"]
            if zone:
                intra.setdefault(zone, []).append(entry)
            # else: neither endpoint nor the line's own subArea resolves — drop.

    return inter, intra


def build_subarea_network(
    subs: list[dict],
    lines: list[dict],
    gens: list[dict],
    demand: dict[str, list[float]],
    *,
    map_lines: list[dict] | None = None,
    demand_split: str = "capacity",
    reference_zone: str | None = None,
) -> tuple[NodalNetwork, dict[str, dict]]:
    """Build a NodalNetwork at subarea granularity.

    demand_split is accepted for interface parity with the node scope but
    unused here: demand is already published per-subarea by XM, so there is
    no split to perform at this granularity.
    """
    map_lines = map_lines or []
    sub_to_subarea = {s["name"]: s["subarea"] for s in subs}
    subarea_names = sorted(
        {sa for sa in sub_to_subarea.values() if sa and sa not in EXCLUDED_SUBAREAS}
    )
    if not subarea_names:
        raise ValueError("no domestic subareas found in substations")

    zones = [Zone(name=name) for name in subarea_names]

    generators = [
        Generator(
            name=g["name"],
            zone=g["subarea"],
            p_max=g["capacity"],
            marginal_cost=g["marginal_cost"],
            fuel=g["fuel"],
        )
        for g in gens
        if g["subarea"] in subarea_names
    ]

    inter, intra = _classify_and_collect(map_lines, lines, sub_to_subarea)

    branches = []
    for pair, entries in inter.items():
        a, b = sorted(pair)
        # Guard: skip pairs where either member isn't a valid zone (dangling refs)
        if a not in subarea_names or b not in subarea_names:
            continue
        combined_reactance, combined_rating = _combine_parallel(entries)
        branches.append(
            Branch(
                name=f"{a} - {b}",
                from_zone=a,
                to_zone=b,
                reactance=combined_reactance,
                rating=combined_rating,
            )
        )

    intra_summary: dict[str, dict] = {}
    for zone, entries in intra.items():
        if zone not in subarea_names:
            continue
        _, combined_rating = _combine_parallel(entries)
        intra_summary[zone] = {"rating_mw": combined_rating, "n_lines": len(entries)}

    subarea_total = {name: sum(vals) for name, vals in demand.items()}
    shares = {name: subarea_total.get(name, 0.0) for name in subarea_names}
    total = sum(shares.values())
    if total <= 0:
        raise ValueError("demand produced zero total energy; check demand source/date")
    demand_shares = {z: v / total for z, v in shares.items()}

    ref = reference_zone or subarea_names[0]
    network = NodalNetwork(
        reference_zone=ref,
        zones=zones,
        generators=generators,
        branches=branches,
        demand_shares=demand_shares,
    )
    return network, intra_summary
