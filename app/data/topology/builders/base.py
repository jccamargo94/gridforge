from __future__ import annotations

from typing import Any, Protocol

from app.nodal.network.schemas import NodalNetwork


class TopologyBuilder(Protocol):
    """Shared contract for every zone-granularity implementation.

    Every implementation accepts the same arguments (map_lines is ignored by
    scopes that don't need it) and returns (network, extra) — extra is
    scope-specific auxiliary data not part of the NodalNetwork schema itself
    (an empty dict when the scope has none).
    """

    def __call__(
        self,
        subs: list[dict],
        lines: list[dict],
        gens: list[dict],
        demand: dict[str, list[float]],
        *,
        map_lines: list[dict] | None = None,
        demand_split: str = "capacity",
        reference_zone: str | None = None,
    ) -> tuple[NodalNetwork, dict[str, Any]]: ...
