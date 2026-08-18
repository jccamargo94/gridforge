from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Settlement:
    regime: str
    energy_price: list[float]
    zone_load_payment: dict[str, list[float]]
    gen_revenue: dict[str, list[float]]
    congestion_rent: list[float]
    total_load_payment: float
    total_gen_revenue: float
    uplift: list[float] | None = None
