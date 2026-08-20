from __future__ import annotations

from typing import Any

from app.data.topology.build import build_network
from app.nodal.network.schemas import NodalNetwork


def build_node_network(
    subs: list[dict],
    lines: list[dict],
    gens: list[dict],
    demand: dict[str, list[float]],
    *,
    map_lines: list[dict] | None = None,
    demand_split: str = "capacity",
    reference_zone: str | None = None,
) -> tuple[NodalNetwork, dict[str, Any]]:
    """Node (per-substation) scope: thin wrapper around the existing build_network.

    map_lines is accepted for interface uniformity but unused at this scope.
    """
    network = build_network(
        subs, lines, gens, demand, demand_split=demand_split, reference_zone=reference_zone
    )
    return network, {}
