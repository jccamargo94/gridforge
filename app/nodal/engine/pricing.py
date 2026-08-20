from __future__ import annotations


def demand_weighted_average_price(
    lmp: dict[str, list[float]],
    loads: dict[str, list[float]],
    buses: list[str],
    n_hours: int,
) -> list[float]:
    return [
        sum(lmp[b][t] * loads[b][t] for b in buses) / sum(loads[b][t] for b in buses)
        for t in range(n_hours)
    ]


def congestion_component(
    lmp: dict[str, list[float]],
    avg_price: list[float],
    buses: list[str],
    n_hours: int,
) -> dict[str, list[float]]:
    return {b: [lmp[b][t] - avg_price[t] for t in range(n_hours)] for b in buses}
