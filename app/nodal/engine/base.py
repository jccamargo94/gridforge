from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.nodal.network.schemas import NodalNetwork


@dataclass
class NodalSolution:
    timestamps: list[str]
    buses: list[str]
    reference_zone: str
    lmp: dict[str, list[float]]
    dispatch: dict[str, list[float]]
    loads: dict[str, list[float]]
    branch_flows: dict[str, list[float]]
    commitment: dict[str, list[float]]
    gen_cost: dict[str, list[float]]
    gen_zone: dict[str, str]
    gen_fuel: dict[str, str]
    total_cost: float
    uc_total_cost: float | None = None


class NodalEngine(Protocol):
    def solve(
        self,
        net: NodalNetwork,
        *,
        solver: str = "cbc",
        use_unit_commitment: bool = True,
        mipgap: float = 0.01,
        timelimit: float = 120.0,
    ) -> NodalSolution: ...
