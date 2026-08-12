"""Orchestrate dispatch runs: ensure data -> build -> solve -> save -> evaluate.

Per-case failures are isolated: one bad case does not abort the batch.
"""

import traceback

import pandas as pd
from sqlalchemy.orm import Session

from app.data.actuals import load_actual_dispatch, load_actual_price
from app.data.heuristic.biddings import _match_resource_name
from app.model.model import UnitCommitmentModel
from app.pipeline.case_builder import build_case
from app.pipeline.results import extract_dispatch, extract_mpo, save_results
from app.schemas import DispatchCase, InputPack, InputSource, RunResult
from app.storage import get_storage
from app.utils.metrics import mae, price_metrics, rmse


def run_case(
    case: DispatchCase,
    *,
    evaluate: bool = True,
    input_source: InputSource = InputSource.historical,
    ders: int | None = None,
    out: str = "data/results",
    data_dir: str = "data",
    session: Session | None = None,
) -> RunResult:
    t = case.level.value
    try:
        inputs = InputPack(dispatch_date=case.dispatch_date, source=input_source, data_dir=data_dir)
        set_data, param_data, _meta = build_case(case, inputs, ders=ders, session=session)
        model = UnitCommitmentModel(case=case)
        model.create_model(set_data=set_data, param_data=param_data)
        model.solve(solver=case.solver, compute_prices=case.compute_prices)
        result = save_results(model, case, out=out)

        if evaluate:
            try:
                xm = load_actual_price(case.dispatch_date, data_dir=data_dir)
                model_mpo = extract_mpo_sorted(model)
                n = min(len(xm), len(model_mpo))
                metrics = price_metrics(xm[:n], model_mpo[:n])
            except (FileNotFoundError, ValueError):
                print(f"  ! no XM actuals for {case.dispatch_date}; skipping metrics")
                metrics = None

            if metrics is not None:
                try:
                    metrics.update(_dispatch_metrics(model, case.dispatch_date, data_dir))
                except (FileNotFoundError, ValueError):
                    print(
                        f"  ! no PrId actuals for {case.dispatch_date}; skipping dispatch metrics"
                    )
                metrics_path = f"{out}/metrics-{case.dispatch_date}-{t}.csv"
                pd.DataFrame([metrics]).to_csv(metrics_path, index=False)
                result.metrics = metrics
                result.metrics_path = metrics_path

        return result
    except Exception as e:
        traceback.print_exc()
        return RunResult(case=case, ok=False, error=f"{type(e).__name__}: {e}")


def _dispatch_metrics(model, dispatch_date, data_dir: str) -> dict[str, float]:
    """MAE/RMSE (MW) of model dispatch vs the PrId predespacho ideal, aligned
    per matched resource. PrId raw resource names are matched to model
    generator names via the existing fuzzy matcher; unmatched resources are
    skipped. Returns an empty dict when nothing matches."""
    actual = load_actual_dispatch(dispatch_date, data_dir=data_dir)
    model_dispatch = extract_dispatch(model)
    resource_names = sorted(model_dispatch["generador"].unique())

    actual_mw: list[float] = []
    model_mw: list[float] = []
    for raw_name, values in actual.items():
        matched = _match_resource_name(raw_name, resource_names)
        if matched is None:
            continue
        sub = model_dispatch[model_dispatch["generador"] == matched].sort_values("datetime")
        if len(sub) != len(values):
            continue
        actual_mw.extend(values)
        model_mw.extend(sub["dispatch"].astype(float).tolist())

    if not actual_mw:
        return {}
    return {
        "dispatch_mae_mw": mae(actual_mw, model_mw),
        "dispatch_rmse_mw": rmse(actual_mw, model_mw),
    }


def extract_mpo_sorted(model) -> list[float]:
    mpo = extract_mpo(model)
    return [v for _, v in sorted(mpo.items())]


def run_many(
    cases: list[DispatchCase],
    *,
    out: str = "data/results",
    session: Session | None = None,
    **kw,
) -> list[RunResult]:
    results: list[RunResult] = []
    for case in cases:
        print(f"==> {case.dispatch_date} [{case.level.value}]")
        results.append(run_case(case, out=out, session=session, **kw))

    rows = [
        {
            "date": r.case.dispatch_date,
            "type": r.case.level.value,
            "scenario": (
                r.case.bess_scenario.penetration_level
                if r.case.bess_scenario is not None
                else "baseline"
            ),
            **(r.metrics or {}),
            **(r.bess_summary or {}),
        }
        for r in results
        if r.ok
    ]
    if rows:
        storage = get_storage(out)
        with storage.open("metrics-summary.csv", "w") as f:
            pd.DataFrame(rows).to_csv(f, index=False)
    return results
