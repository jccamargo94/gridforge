from __future__ import annotations

from typing import Any

from app.data.topology.builders.node import build_node_network
from app.nodal.network.schemas import NodalNetwork


def build_area_network(
    subs: list[dict],
    lines: list[dict],
    gens: list[dict],
    demand: dict[str, list[float]],
    *,
    map_lines: list[dict] | None = None,
    demand_split: str = "capacity",
    reference_zone: str | None = None,
) -> tuple[NodalNetwork, dict[str, Any]]:
    """Area scope: not implemented.

    PARATEC has no line-level data at area granularity (only 8 areas, no
    branch source) — this would require aggregating subarea results, which
    is out of scope for this change.
    """
    raise NotImplementedError(
        "scope='area' has no line-level PARATEC data source; "
        "requires subarea-to-area aggregation, not yet implemented"
    )


BUILDERS = {
    "node": build_node_network,
    "area": build_area_network,
}
