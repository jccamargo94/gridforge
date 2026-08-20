from __future__ import annotations

from app.nodal.engine.base import NodalSolution
from app.nodal.settlement.base import Settlement
from app.nodal.settlement.rent import congestion_rent


def settle_status_quo(sol: NodalSolution) -> Settlement:
    n = len(sol.timestamps)
    energy_price = list(sol.lmp_avg)
    congestion_rents = [congestion_rent(sol, t) for t in range(n)]
    total_load = [sum(sol.loads[b][t] for b in sol.buses) for t in range(n)]

    zone_load_payment: dict[str, list[float]] = {b: [] for b in sol.buses}
    for b in sol.buses:
        for t in range(n):
            uplift_share = congestion_rents[t] * sol.loads[b][t] / total_load[t]
            zone_load_payment[b].append(energy_price[t] * sol.loads[b][t] + uplift_share)

    gen_revenue: dict[str, list[float]] = {g: [] for g in sol.dispatch}
    for g in sol.dispatch:
        gen_revenue[g] = [energy_price[t] * sol.dispatch[g][t] for t in range(n)]

    return Settlement(
        regime="status_quo",
        energy_price=energy_price,
        zone_load_payment=zone_load_payment,
        gen_revenue=gen_revenue,
        congestion_rent=congestion_rents,
        total_load_payment=sum(sum(v) for v in zone_load_payment.values()),
        total_gen_revenue=sum(sum(v) for v in gen_revenue.values()),
        uplift=congestion_rents,
    )
