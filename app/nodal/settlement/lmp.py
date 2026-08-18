from __future__ import annotations

from app.nodal.engine.base import NodalSolution
from app.nodal.settlement.base import Settlement
from app.nodal.settlement.rent import congestion_rent


def settle_lmp(sol: NodalSolution) -> Settlement:
    n = len(sol.timestamps)
    zone_load_payment: dict[str, list[float]] = {
        b: [sol.lmp[b][t] * sol.loads[b][t] for t in range(n)] for b in sol.buses
    }
    gen_revenue: dict[str, list[float]] = {
        g: [sol.lmp[sol.gen_zone[g]][t] * sol.dispatch[g][t] for t in range(n)]
        for g in sol.dispatch
    }
    return Settlement(
        regime="lmp",
        energy_price=[],
        zone_load_payment=zone_load_payment,
        gen_revenue=gen_revenue,
        congestion_rent=[congestion_rent(sol, t) for t in range(n)],
        total_load_payment=sum(sum(v) for v in zone_load_payment.values()),
        total_gen_revenue=sum(sum(v) for v in gen_revenue.values()),
        uplift=None,
    )
