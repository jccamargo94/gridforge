from __future__ import annotations

import statistics
from dataclasses import dataclass

import pandas as pd

from app.nodal.engine.base import NodalSolution
from app.nodal.settlement.base import Settlement


@dataclass
class ComparisonResult:
    metrics: dict[str, float]
    redistribution: pd.DataFrame
    gen_revenue_by_zone: pd.DataFrame


def compare_settlements(a: Settlement, b: Settlement, sol: NodalSolution) -> ComparisonResult:
    zones = list(sol.buses)
    total_load_a = sum(sum(v) for v in a.zone_load_payment.values())
    total_load_b = sum(sum(v) for v in b.zone_load_payment.values())
    total_gen_a = sum(sum(v) for v in a.gen_revenue.values())
    total_gen_b = sum(sum(v) for v in b.gen_revenue.values())

    redistribution = pd.DataFrame(
        {
            "zone": zones,
            "load_payment_a": [sum(a.zone_load_payment[z]) for z in zones],
            "load_payment_b": [sum(b.zone_load_payment[z]) for z in zones],
        }
    )
    redistribution["delta"] = redistribution["load_payment_b"] - redistribution["load_payment_a"]

    rows = []
    for g in sol.dispatch:
        ra = sum(a.gen_revenue[g])
        rb = sum(b.gen_revenue[g])
        rows.append(
            {
                "zone": sol.gen_zone[g],
                "fuel": sol.gen_fuel[g],
                "revenue_a": ra,
                "revenue_b": rb,
                "delta": rb - ra,
            }
        )
    gen_revenue_by_zone = pd.DataFrame(rows)

    metrics: dict[str, float] = {
        "total_cost": sol.total_cost,
        "total_load_payment_a": total_load_a,
        "total_load_payment_b": total_load_b,
        "load_payment_delta": total_load_b - total_load_a,
        "total_gen_revenue_a": total_gen_a,
        "total_gen_revenue_b": total_gen_b,
        "gen_revenue_delta": total_gen_b - total_gen_a,
        "congestion_rent_total": sum(a.congestion_rent),
    }
    for z in zones:
        prices = sol.lmp[z]
        metrics[f"price_avg_{z}"] = sum(prices) / len(prices)
        metrics[f"price_vol_{z}"] = statistics.pstdev(prices) if len(prices) > 1 else 0.0

    return ComparisonResult(
        metrics=metrics,
        redistribution=redistribution,
        gen_revenue_by_zone=gen_revenue_by_zone,
    )
