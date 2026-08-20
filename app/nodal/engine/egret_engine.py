from __future__ import annotations

from egret.models.dcopf import solve_dcopf
from egret.models.unit_commitment import solve_unit_commitment

from app.nodal.engine.base import NodalSolution
from app.nodal.engine.pricing import congestion_component, demand_weighted_average_price
from app.nodal.network.schemas import NodalNetwork
from app.nodal.network.to_egret import enforce_commitment, model_data_for_hour, nodal_to_model_data


def _default_time_keys() -> list[str]:
    return [f"H{h:02d}" for h in range(24)]


class EgretNodalEngine:
    def solve(
        self,
        net: NodalNetwork,
        *,
        solver: str = "cbc",
        use_unit_commitment: bool = True,
        mipgap: float = 0.01,
        timelimit: float = 120.0,
    ) -> NodalSolution:
        time_keys = _default_time_keys()
        md = nodal_to_model_data(net, time_keys)

        if use_unit_commitment:
            md_uc = solve_unit_commitment(
                md,
                solver,
                mipgap=mipgap,
                timelimit=timelimit,
                solver_tee=False,
                network_constraints="btheta_power_flow",
            )
            commitment = {
                g: list(gen["commitment"]["values"]) for g, gen in md_uc.elements("generator")
            }
            uc_total_cost = float(md_uc.data["system"]["total_cost"])
        else:
            commitment = {g.name: [1.0] * len(time_keys) for g in net.generators}
            uc_total_cost = None

        lmp: dict[str, list[float]] = {z.name: [] for z in net.zones}
        loads: dict[str, list[float]] = {z.name: [] for z in net.zones}
        dispatch: dict[str, list[float]] = {g.name: [] for g in net.generators}
        branch_flows: dict[str, list[float]] = {b.name: [] for b in net.branches}
        gen_cost: dict[str, list[float]] = {g.name: [] for g in net.generators}
        marginal = {g.name: g.marginal_cost for g in net.generators}
        no_load = {g.name: g.no_load_cost for g in net.generators}

        for t, tk in enumerate(time_keys):
            hour_md = enforce_commitment(net, model_data_for_hour(md, tk), commitment, t)
            hour_md.data["system"]["time_keys"] = [tk]
            out = solve_dcopf(hour_md, solver, solver_tee=False)
            for z in net.zones:
                bus = out.data["elements"]["bus"][z.name]
                lmp[z.name].append(float(bus["lmp"]))
                loads[z.name].append(float(bus["pl"]))
            for g in net.generators:
                gen = out.data["elements"]["generator"][g.name]
                pg = float(gen["pg"])
                dispatch[g.name].append(pg)
                gen_cost[g.name].append(pg * marginal[g.name] + no_load[g.name])
            for b in net.branches:
                branch_flows[b.name].append(float(out.data["elements"]["branch"][b.name]["pf"]))

        zone_names = [z.name for z in net.zones]
        lmp_avg = demand_weighted_average_price(lmp, loads, zone_names, len(time_keys))
        lmp_congestion = congestion_component(lmp, lmp_avg, zone_names, len(time_keys))

        total_cost = sum(sum(v) for v in gen_cost.values())
        return NodalSolution(
            timestamps=time_keys,
            buses=[z.name for z in net.zones],
            reference_zone=net.reference_zone,
            lmp=lmp,
            lmp_avg=lmp_avg,
            lmp_congestion=lmp_congestion,
            dispatch=dispatch,
            loads=loads,
            branch_flows=branch_flows,
            commitment={g.name: list(commitment[g.name]) for g in net.generators},
            gen_cost=gen_cost,
            gen_zone={g.name: g.zone for g in net.generators},
            gen_fuel={g.name: g.fuel for g in net.generators},
            total_cost=total_cost,
            uc_total_cost=uc_total_cost,
        )
