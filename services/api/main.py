import json
import os
from datetime import date

import httpx
import pandas as pd
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, ValidationError

from app.data.actuals import load_reference_price
from app.data.topology import service as topology_service
from app.db import queries
from app.db.session import get_engine, get_sessionmaker
from app.nodal.network.schemas import NodalNetwork
from app.schemas import BessScenario, DispatchLevel
from app.storage import get_storage
from services.api.auth import get_current_user_id

TOPOLOGY_DATASET = "topology_network"
TOPOLOGY_PARTITION = "colombia"
TOPOLOGY_NETWORK_PATH = "topology/network.json"

app = FastAPI(title="gridforge API")

_frontend_origins = [
    origin.strip() for origin in os.environ.get("FRONTEND_ORIGIN", "").split(",") if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_frontend_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

_engine = None
_session_local = None


def get_session():
    global _engine, _session_local
    if _session_local is None:
        _engine = get_engine()
        _session_local = get_sessionmaker(_engine)
    session = _session_local()
    try:
        yield session
    finally:
        session.close()


@app.post("/scenarios")
def create_scenario(
    scenario: BessScenario,
    user_id: str = Depends(get_current_user_id),
    session=Depends(get_session),
):
    row = queries.create_scenario(session, scenario, created_by=user_id)
    return {"id": row.id}


@app.get("/scenarios")
def list_scenarios_endpoint(
    user_id: str = Depends(get_current_user_id), session=Depends(get_session)
):
    scenarios = queries.list_scenarios(session)
    return [
        {
            "id": s.id,
            "mode": s.mode,
            "penetration_level": s.penetration_level,
            "units": s.units,
            "created_at": s.created_at,
        }
        for s in scenarios
    ]


class RunCreateRequest(BaseModel):
    dispatch_date: date
    level: DispatchLevel
    solver: str = "cbc"
    compute_prices: bool = True
    scenario_id: str | None = None
    nodal_network: NodalNetwork | None = None
    recompute_demand_shares: bool = False


def _run_summary(run, case) -> dict:
    return {
        "run_id": run.id,
        "status": run.status,
        "dispatch_date": case.dispatch_date,
        "level": case.level,
        "scenario_id": case.scenario_id,
        "created_at": run.created_at,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "error": run.error,
    }


def _price_comparison_df(run, case) -> pd.DataFrame | None:
    """Model MPO (from run.price_path) aligned with XM MPO (iMAR), sorted by
    datetime, truncated to the shorter series. None when either source is
    missing or unparseable."""
    if run.price_path is None:
        return None
    storage = get_storage(".")
    if not storage.exists(run.price_path):
        return None
    try:
        with storage.open(run.price_path) as f:
            df = pd.read_csv(f, parse_dates=["datetime"])
        xm = load_reference_price(case.dispatch_date, level=case.level, data_dir="data")
    except (FileNotFoundError, ValueError):
        return None
    df = df.sort_values("datetime")
    model_mpo = df["ideal_marginal_price"].astype(float).tolist()
    n = min(len(model_mpo), len(xm))
    return pd.DataFrame(
        {
            "datetime": [str(dt) for dt in df["datetime"].tolist()[:n]],
            "model_mpo": model_mpo[:n],
            "xm_mpo": [float(x) for x in xm[:n]],
        }
    )


def _price_series(run, case) -> list[dict] | None:
    df = _price_comparison_df(run, case)
    if df is None:
        return None
    return df.to_dict(orient="records")


def _nodal_summary(session, run_id: str) -> dict | None:
    nodal = queries.get_nodal_result(session, run_id)
    if nodal is None or not nodal.network:
        return None
    net = nodal.network
    return {
        "network_name": net.get("name"),
        "zones": len(net.get("zones", [])),
        "generators": len(net.get("generators", [])),
        "branches": len(net.get("branches", [])),
    }


def _get_owned_run(session, run_id: str, user_id: str):
    run = queries.get_run(session, run_id)
    if run is None or run.user_id != user_id:
        raise HTTPException(status_code=404, detail="run not found")
    return run


@app.post("/runs")
def create_run(
    body: RunCreateRequest,
    user_id: str = Depends(get_current_user_id),
    session=Depends(get_session),
):
    if body.scenario_id is not None and queries.get_scenario(session, body.scenario_id) is None:
        raise HTTPException(status_code=404, detail="scenario not found")
    if body.nodal_network is not None and body.level != DispatchLevel.lmp:
        raise HTTPException(status_code=400, detail="nodal_network is only valid for level lmp")
    if body.recompute_demand_shares and body.nodal_network is None:
        raise HTTPException(
            status_code=400, detail="recompute_demand_shares requires nodal_network"
        )

    nodal_network_dict = body.nodal_network.model_dump() if body.nodal_network else None
    if body.recompute_demand_shares:
        zone_names = [z["name"] for z in nodal_network_dict["zones"]]
        try:
            shares, _source = topology_service.recompute_demand_shares(
                get_storage("data"), body.dispatch_date, zone_names
            )
        except (httpx.HTTPStatusError, ValueError) as exc:
            raise HTTPException(
                status_code=422, detail=f"could not recompute demand shares: {exc}"
            ) from exc
        nodal_network_dict["demand_shares"] = shares
        try:
            NodalNetwork(**nodal_network_dict)
        except ValidationError as exc:
            raise HTTPException(
                status_code=422, detail=f"recomputed demand shares invalid: {exc}"
            ) from exc

    run = queries.create_case_and_run(
        session,
        dispatch_date=body.dispatch_date,
        level=body.level.value,
        solver=body.solver,
        compute_prices=body.compute_prices,
        scenario_id=body.scenario_id,
        user_id=user_id,
        nodal_network=nodal_network_dict,
    )
    return {"run_id": run.id, "status": run.status}


class TopologyScrapeRequest(BaseModel):
    dispatch_date: date
    demand_source: str = "ddem"


@app.post("/topology/scrape")
def scrape_topology(
    body: TopologyScrapeRequest,
    user_id: str = Depends(get_current_user_id),
    session=Depends(get_session),
):
    """Fetch fresh PARATEC + XM data and overwrite the cached Colombian network.

    Not yet wired to any frontend action — trigger manually (e.g. via curl)
    until scrape scheduling/admin-gating is built. See README.
    """
    if body.demand_source not in ("ddem", "pron"):
        raise HTTPException(status_code=400, detail="demand_source must be 'ddem' or 'pron'")
    storage = get_storage("data")
    try:
        network, _extra = topology_service.scrape_topology(
            storage, body.dispatch_date, demand_source=body.demand_source, scope="subarea"
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"PARATEC/XM fetch failed: {exc}") from exc
    with storage.open(TOPOLOGY_NETWORK_PATH, "w") as fh:
        json.dump(network.model_dump(), fh, indent=2, ensure_ascii=False)
    queries.upsert_input_dataset(
        session,
        dataset=TOPOLOGY_DATASET,
        partition_key=TOPOLOGY_PARTITION,
        source=f"paratec:subarea:{body.demand_source}:{body.dispatch_date}",
        row_count=len(network.zones),
    )
    return {
        "zones": len(network.zones),
        "generators": len(network.generators),
        "branches": len(network.branches),
    }


@app.get("/topology/network")
def get_topology_network(user_id: str = Depends(get_current_user_id), session=Depends(get_session)):
    """Return the cached Colombian network last written by POST /topology/scrape."""
    storage = get_storage("data")
    if not storage.exists(TOPOLOGY_NETWORK_PATH):
        raise HTTPException(
            status_code=404, detail="no cached network yet; run POST /topology/scrape"
        )
    with storage.open(TOPOLOGY_NETWORK_PATH) as fh:
        network = json.load(fh)
    dataset = queries.get_input_dataset(session, TOPOLOGY_DATASET, TOPOLOGY_PARTITION)
    return {"network": network, "scraped_at": dataset.fetched_at if dataset else None}


@app.get("/runs")
def list_runs(user_id: str = Depends(get_current_user_id), session=Depends(get_session)):
    runs = queries.list_runs_for_user(session, user_id)
    return [
        {
            **_run_summary(r, queries.get_case(session, r.case_id)),
            "nodal": _nodal_summary(session, r.id),
        }
        for r in runs
    ]


@app.get("/runs/{run_id}")
def get_run_detail(
    run_id: str, user_id: str = Depends(get_current_user_id), session=Depends(get_session)
):
    run = _get_owned_run(session, run_id, user_id)
    case = queries.get_case(session, run.case_id)
    metric_set = queries.get_metric_set(session, run.id)
    out = _run_summary(run, case)
    out["metrics"] = (
        {
            "rmse": metric_set.rmse,
            "mae": metric_set.mae,
            "bias": metric_set.bias,
            "wape": metric_set.wape,
            "smape": metric_set.smape,
            "r2": metric_set.r2,
            "bess_charge_mwh": metric_set.bess_charge_mwh,
            "bess_discharge_mwh": metric_set.bess_discharge_mwh,
            "bess_avg_soc_mwh": metric_set.bess_avg_soc_mwh,
            "bess_net_revenue": metric_set.bess_net_revenue,
            "dispatch_mae_mw": metric_set.dispatch_mae_mw,
            "dispatch_rmse_mw": metric_set.dispatch_rmse_mw,
        }
        if metric_set
        else None
    )
    out["artifacts"] = {
        "dispatch": run.dispatch_path is not None,
        "prices": run.price_path is not None,
        "bess": run.bess_path is not None,
        "marginal_plants": run.marginal_plants_path is not None,
    }
    out["price_series"] = _price_series(run, case)
    nodal_result = queries.get_nodal_result(session, run.id)
    out["nodal"] = (
        {
            "metrics": nodal_result.metrics,
            "redistribution": nodal_result.redistribution,
            "gen_revenue_by_zone": nodal_result.gen_revenue_by_zone,
            "network": nodal_result.network,
            "artifacts": {
                name: getattr(nodal_result, attr) is not None
                for name, attr in _NODAL_ARTIFACT_PATHS.items()
            },
        }
        if nodal_result
        else None
    )
    return out


@app.get("/runs/{run_id}/log")
def get_run_log(
    run_id: str, user_id: str = Depends(get_current_user_id), session=Depends(get_session)
):
    run = _get_owned_run(session, run_id, user_id)
    if run.log_path is None or not get_storage(".").exists(run.log_path):
        raise HTTPException(status_code=404, detail="run has no log yet")
    with get_storage(".").open(run.log_path) as f:
        content = f.read()
    return PlainTextResponse(content)


_ARTIFACT_PATHS = {
    "dispatch": "dispatch_path",
    "prices": "price_path",
    "bess": "bess_path",
    "marginal_plants": "marginal_plants_path",
}

_NODAL_ARTIFACT_PATHS = {
    "lmp": "lmp_path",
    "dispatch": "dispatch_path",
    "branch_flows": "branch_flows_path",
    "settlement_status_quo": "settlement_status_quo_path",
    "settlement_lmp": "settlement_lmp_path",
    "comparison": "comparison_path",
    "summary": "summary_path",
}


def _get_owned_nodal_result(session, run, artifact: str):
    nodal = queries.get_nodal_result(session, run.id)
    if nodal is None:
        raise HTTPException(status_code=404, detail="run has no nodal results yet")
    attr = _NODAL_ARTIFACT_PATHS.get(artifact)
    if attr is None:
        raise HTTPException(status_code=404, detail="unknown artifact")
    path = getattr(nodal, attr)
    if path is None:
        raise HTTPException(status_code=404, detail=f"run has no {artifact} artifact yet")
    if not get_storage(".").exists(path):
        raise HTTPException(status_code=404, detail="artifact file missing on disk")
    return nodal, path


def _artifact_path(run, artifact: str) -> str:
    if artifact not in _ARTIFACT_PATHS:
        raise HTTPException(status_code=404, detail="unknown artifact")
    path = getattr(run, _ARTIFACT_PATHS[artifact])
    if path is None:
        raise HTTPException(status_code=404, detail=f"run has no {artifact} artifact yet")
    if not get_storage(".").exists(path):
        raise HTTPException(status_code=404, detail="artifact file missing on disk")
    return path


@app.get("/runs/{run_id}/{artifact}")
def get_run_artifact(
    run_id: str,
    artifact: str,
    user_id: str = Depends(get_current_user_id),
    session=Depends(get_session),
):
    run = _get_owned_run(session, run_id, user_id)
    path = _artifact_path(run, artifact)
    with get_storage(".").open(path) as f:
        df = pd.read_csv(f)
    return df.to_dict(orient="records")


@app.get("/runs/{run_id}/download/price_comparison")
def download_price_comparison(
    run_id: str,
    user_id: str = Depends(get_current_user_id),
    session=Depends(get_session),
):
    run = _get_owned_run(session, run_id, user_id)
    case = queries.get_case(session, run.case_id)
    df = _price_comparison_df(run, case)
    if df is None:
        raise HTTPException(status_code=404, detail="price data not available")
    return PlainTextResponse(
        df.to_csv(index=False),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=price_comparison.csv"},
    )


@app.get("/runs/{run_id}/download/{artifact}")
def download_run_artifact(
    run_id: str,
    artifact: str,
    user_id: str = Depends(get_current_user_id),
    session=Depends(get_session),
):
    run = _get_owned_run(session, run_id, user_id)
    path = _artifact_path(run, artifact)
    return FileResponse(path)


def _normalize_nodal_artifact(artifact: str) -> str:
    if artifact.endswith(".csv") or artifact.endswith(".json"):
        return artifact[: -len(".csv")] if artifact.endswith(".csv") else artifact[: -len(".json")]
    return artifact


@app.get("/runs/{run_id}/nodal/{artifact}")
def get_nodal_artifact(
    run_id: str,
    artifact: str,
    user_id: str = Depends(get_current_user_id),
    session=Depends(get_session),
):
    run = _get_owned_run(session, run_id, user_id)
    nodal, path = _get_owned_nodal_result(session, run, artifact)
    if artifact == "summary":
        with get_storage(".").open(path) as f:
            return json.load(f)
    try:
        with get_storage(".").open(path) as f:
            df = pd.read_csv(f)
    except (pd.errors.EmptyDataError, ValueError) as exc:
        raise HTTPException(
            status_code=404, detail=f"artifact {artifact} is not a readable CSV"
        ) from exc
    return df.astype(object).where(pd.notnull(df), None).to_dict(orient="records")


@app.get("/runs/{run_id}/download/nodal/{artifact}")
def download_nodal_artifact(
    run_id: str,
    artifact: str,
    user_id: str = Depends(get_current_user_id),
    session=Depends(get_session),
):
    run = _get_owned_run(session, run_id, user_id)
    logical = _normalize_nodal_artifact(artifact)
    _, path = _get_owned_nodal_result(session, run, logical)
    return FileResponse(path)
