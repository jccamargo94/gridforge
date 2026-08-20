from __future__ import annotations

import json
from datetime import date

from app.data.heuristic.biddings import _match_resource_name, ensure_ofertas_estimado
from app.data.loaders import load_demanda, load_dispo, load_ofertas
from app.nodal.engine.egret_engine import EgretNodalEngine
from app.nodal.network.schemas import BusLoad, Generator, NodalNetwork
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
        BusLoad(zone=z, p_load=[hourly[t] * 1e-3 * net.demand_shares[z] for t in range(24)])
        for z in net.demand_shares
    ]


def build_generator_costs(net: NodalNetwork, dispatch_date: date, data_dir: str) -> list[Generator]:
    # Real, per-day market price (ofertas) overrides the static topology-scrape
    # fallback (parse.py's _cost_for) -- mirrors build_zonal_loads attaching
    # real demand at run time instead of scrape time. demand_shares is only
    # ever set by the real topology builders (never by synthetic/example
    # networks), so it doubles as "this network has matching market data".
    if not net.demand_shares:
        return list(net.generators)
    try:
        oferta_full = load_ofertas(data_dir, dispatch_date.year)
        day = oferta_full[oferta_full["Date"].dt.date == dispatch_date]
        if day.empty:
            dispo = load_dispo(data_dir, dispatch_date.year)
            day_dispo = dispo[dispo["datetime"].dt.date == dispatch_date]
            day = ensure_ofertas_estimado(dispatch_date, data_dir, day_dispo, oferta_full)
    except (FileNotFoundError, ValueError):
        return list(net.generators)
    if day.empty:
        return list(net.generators)

    price_by_resource = day.groupby("resource_name")["Value"].last().to_dict()
    resource_names = list(price_by_resource.keys())
    updated = []
    for g in net.generators:
        matched = _match_resource_name(g.name, resource_names)
        cost = price_by_resource[matched] if matched is not None else g.marginal_cost
        updated.append(g.model_copy(update={"marginal_cost": cost}))
    return updated


def run_nodal(
    case: DispatchCase, *, out: str = "data/results", data_dir: str = "data"
) -> RunResult:
    try:
        net = load_network(case.nodal_network)
        net = net.model_copy(
            update={
                "loads": build_zonal_loads(net, case.dispatch_date, data_dir),
                "generators": build_generator_costs(net, case.dispatch_date, data_dir),
            }
        )
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
