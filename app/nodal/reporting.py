from __future__ import annotations

import json

import pandas as pd

from app.nodal.engine.base import NodalSolution
from app.nodal.settlement.base import Settlement
from app.nodal.settlement.compare import ComparisonResult
from app.storage import get_storage


def save_nodal_artifacts(
    sol: NodalSolution,
    a: Settlement,
    b: Settlement,
    comparison: ComparisonResult,
    *,
    out_dir: str,
) -> dict[str, str]:
    storage = get_storage(out_dir)

    lmp_rows = [
        {
            "timestamp": ts,
            "bus": bus,
            "lmp": sol.lmp[bus][t],
            "lmp_avg": sol.lmp_avg[t],
            "lmp_congestion": sol.lmp_congestion[bus][t],
        }
        for t, ts in enumerate(sol.timestamps)
        for bus in sol.buses
    ]
    dispatch_rows = [
        {
            "generator": g,
            "zone": sol.gen_zone[g],
            "fuel": sol.gen_fuel[g],
            "hour": t,
            "dispatch_mw": sol.dispatch[g][t],
        }
        for t in range(len(sol.timestamps))
        for g in sol.dispatch
    ]
    flow_rows = [
        {"timestamp": ts, "branch": br, "flow_mw": sol.branch_flows[br][t]}
        for t, ts in enumerate(sol.timestamps)
        for br in sol.branch_flows
    ]

    gen_zone = sol.gen_zone
    sq_rows = []
    lmp_rows_settle = []
    for t in range(len(sol.timestamps)):
        for z in sol.buses:
            z_gen_rev = sum(a.gen_revenue[g][t] for g in sol.dispatch if gen_zone[g] == z)
            sq_rows.append(
                {
                    "zone": z,
                    "hour": t,
                    "load_payment": a.zone_load_payment[z][t],
                    "gen_revenue": z_gen_rev,
                    "uplift": a.uplift[t],
                }
            )
            z_gen_rev_b = sum(b.gen_revenue[g][t] for g in sol.dispatch if gen_zone[g] == z)
            lmp_rows_settle.append(
                {
                    "zone": z,
                    "hour": t,
                    "load_payment": b.zone_load_payment[z][t],
                    "gen_revenue": z_gen_rev_b,
                }
            )

    frames = {
        "lmp": pd.DataFrame(lmp_rows),
        "dispatch": pd.DataFrame(dispatch_rows),
        "branch_flows": pd.DataFrame(flow_rows),
        "settlement_status_quo": pd.DataFrame(sq_rows),
        "settlement_lmp": pd.DataFrame(lmp_rows_settle),
        "comparison": comparison.redistribution,
    }
    paths: dict[str, str] = {}
    for name, df in frames.items():
        rel = f"{name}.csv"
        with storage.open(rel, "w") as f:
            df.to_csv(f, index=False)
        paths[name] = rel

    summary = {
        "metrics": comparison.metrics,
        "totals": {
            "total_cost": sol.total_cost,
            "total_load_payment_a": a.total_load_payment,
            "total_load_payment_b": b.total_load_payment,
            "total_gen_revenue_a": a.total_gen_revenue,
            "total_gen_revenue_b": b.total_gen_revenue,
            "congestion_rent_total": sum(a.congestion_rent),
        },
        "generator_count": len(sol.dispatch),
        "branch_count": len(sol.branch_flows),
    }
    with storage.open("summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    paths["summary.json"] = "summary.json"

    return paths
