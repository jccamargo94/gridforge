from __future__ import annotations

import json
from datetime import date

from app.data.loaders import load_demanda
from app.nodal.engine.egret_engine import EgretNodalEngine
from app.nodal.network.schemas import BusLoad, NodalNetwork
from app.nodal.reporting import save_nodal_artifacts
from app.nodal.settlement.compare import compare_settlements
from app.nodal.settlement.lmp import settle_lmp
from app.nodal.settlement.status_quo import settle_status_quo
from app.schemas import DispatchCase, NodalRunResult, RunResult
from app.storage import get_storage


def load_network(network_path: str | None) -> NodalNetwork:
    if network_path:
        storage = get_storage(".")
        with storage.open(network_path) as f:
            return NodalNetwork.model_validate(json.load(f))
    from importlib.resources import files

    path = files("app.nodal.data").joinpath("example_zonal_network.json")
    return NodalNetwork.model_validate(json.loads(path.read_text()))


def build_zonal_loads(net: NodalNetwork, dispatch_date: date, data_dir: str) -> list[BusLoad]:
    if not net.demand_shares:
        return list(net.loads)
    df = load_demanda(data_dir, dispatch_date.year)
    day = df[df["datetime"].dt.date == dispatch_date]
    if day.empty:
        raise ValueError(f"no demand data for {dispatch_date} in {data_dir}")
    hourly = day.sort_values("datetime")["dema"].astype(float).tolist()
    if len(hourly) < 24:
        raise ValueError(f"expected 24 hourly demand rows for {dispatch_date}, got {len(hourly)}")
    return [
        BusLoad(zone=z, p_load=[hourly[t] * net.demand_shares[z] for t in range(24)])
        for z in net.demand_shares
    ]


def run_nodal(
    case: DispatchCase, *, out: str = "data/results", data_dir: str = "data"
) -> RunResult:
    try:
        net = load_network(case.nodal_network)
        net = net.model_copy(update={"loads": build_zonal_loads(net, case.dispatch_date, data_dir)})
        sol = EgretNodalEngine().solve(net, solver=case.solver)
        a = settle_status_quo(sol)
        b = settle_lmp(sol)
        comparison = compare_settlements(a, b, sol)
        out_dir = f"{out}/{case.dispatch_date}-lmp"
        paths = save_nodal_artifacts(sol, a, b, comparison, out_dir=out_dir)
        nodal = NodalRunResult(
            lmp_path=f"{out_dir}/{paths['lmp']}",
            dispatch_path=f"{out_dir}/{paths['dispatch']}",
            branch_flows_path=f"{out_dir}/{paths['branch_flows']}",
            settlement_status_quo_path=f"{out_dir}/{paths['settlement_status_quo']}",
            settlement_lmp_path=f"{out_dir}/{paths['settlement_lmp']}",
            comparison_path=f"{out_dir}/{paths['comparison']}",
            summary_path=f"{out_dir}/{paths['summary.json']}",
            metrics=comparison.metrics,
            redistribution=comparison.redistribution.to_dict(orient="records"),
            gen_revenue_by_zone=comparison.gen_revenue_by_zone.to_dict(orient="records"),
            network=net.model_dump(),
        )
        return RunResult(
            case=case,
            ok=True,
            dispatch_path=nodal.dispatch_path,
            metrics=comparison.metrics,
            nodal=nodal,
        )
    except Exception as e:
        return RunResult(case=case, ok=False, error=f"{type(e).__name__}: {e}")
