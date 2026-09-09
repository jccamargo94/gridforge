"""Execution half of the scheduler: shared solve path + plan/reeval execution.

execute_run is the body of the worker's process_once after its claim,
extracted so the plan tick executes plan runs through the exact same path
(log capture, finish_run_ok/nodal/failed). Plan runs are system runs:
user_id NULL, visibility public, input_grade per kind.
"""

from __future__ import annotations

import contextlib
import io
import json
import logging
import traceback
from datetime import datetime

from app.db import queries
from app.db.claim import claim_run_by_id
from app.pipeline.runner import run_case
from app.scheduler import reeval, timeutil
from app.scheduler.plans import KIND_INPUT_GRADE, KIND_LEVEL
from app.schemas import BessScenario, DispatchCase, DispatchLevel
from app.storage import get_storage


def _build_case(session, case_row) -> DispatchCase:
    scenario = None
    if case_row.scenario_id is not None:
        scenario_row = queries.get_scenario(session, case_row.scenario_id)
        scenario = BessScenario(
            mode=scenario_row.mode,
            penetration_level=scenario_row.penetration_level,
            units=scenario_row.units,
        )
    return DispatchCase(
        dispatch_date=case_row.dispatch_date,
        level=DispatchLevel(case_row.level),
        solver=case_row.solver,
        compute_prices=case_row.compute_prices,
        bess_scenario=scenario,
    )


def execute_run(
    session, run, *, data_dir: str = "data", results_root: str = "data/results"
) -> None:
    """Solve one claimed run to completion; never raises."""
    out_dir = f"{results_root}/{run.id}"
    log_path = f"{out_dir}/run.log"

    try:
        case_row = queries.get_case(session, run.case_id)
        case = _build_case(session, case_row)

        if case_row.nodal_network:
            network_path = f"{out_dir}/network.json"
            with get_storage(".").open(network_path, "w") as f:
                json.dump(case_row.nodal_network, f)
            case.nodal_network = network_path

        # Close the read-only transaction _build_case's queries opened so the
        # session sits idle for the duration of the solve (see worker main.py).
        session.commit()

        log_buffer = io.StringIO()
        log_handler = logging.StreamHandler(log_buffer)
        root_logger = logging.getLogger()
        root_logger.addHandler(log_handler)
        try:
            with contextlib.redirect_stdout(log_buffer), contextlib.redirect_stderr(log_buffer):
                result = run_case(
                    case, evaluate=True, out=out_dir, data_dir=data_dir, session=session
                )
        finally:
            root_logger.removeHandler(log_handler)

        with contextlib.suppress(OSError):
            with get_storage(".").open(log_path, "w") as f:
                f.write(log_buffer.getvalue())
            run.log_path = log_path

        if result.ok:
            if result.nodal is not None:
                queries.finish_nodal_run_ok(session, run, result, out_dir=out_dir)
            else:
                queries.finish_run_ok(session, run, result, out_dir=out_dir)
        else:
            queries.finish_run_failed(
                session, run, result.error or "unknown error", log_path=log_path
            )
    except Exception as exc:
        session.rollback()
        try:
            queries.finish_run_failed(session, run, f"{type(exc).__name__}: {exc}")
        except Exception:
            traceback.print_exc()


def execute_plan(
    session,
    plan,
    *,
    now: datetime,
    config,
    data_dir: str = "data",
    results_root: str = "data/results",
) -> None:
    """Create, claim and solve the run for a run-producing plan kind."""
    # KIND_LEVEL carries plain strings; coerce once so `level.value` and the
    # DispatchLevel comparison below behave like enum members.
    level = DispatchLevel(KIND_LEVEL[plan.kind])
    grade = KIND_INPUT_GRADE[plan.kind]
    nodal_network = None
    if level == DispatchLevel.lmp:
        with get_storage(data_dir).open("topology/network.json") as fh:
            nodal_network = json.load(fh)

    run = queries.create_case_and_run(
        session,
        dispatch_date=plan.target_date,
        level=level.value,
        solver="cbc",
        compute_prices=True,
        scenario_id=None,
        user_id=None,
        nodal_network=nodal_network,
        visibility="public",
        input_grade=grade,
    )
    claimed = claim_run_by_id(session, run.id)
    if claimed is None:
        queries.mark_plan_failed(
            session,
            plan,
            error="run reclamado por otro worker",
            retry_at=timeutil.retry_due(now, config),
        )
        return

    execute_run(session, claimed, data_dir=data_dir, results_root=results_root)

    if claimed.status == "done":
        queries.mark_plan_done(session, plan, run_id=claimed.id)
    else:
        error = claimed.error or "unknown error"
        if plan.attempts >= config.plan_max_attempts:
            queries.mark_plan_failed(session, plan, error=error, run_id=claimed.id)
        else:
            queries.mark_plan_failed(
                session,
                plan,
                error=error,
                run_id=claimed.id,
                retry_at=timeutil.retry_due(now, config),
            )


def execute_reeval(session, plan, *, now: datetime, config, data_dir: str = "data") -> None:
    """Re-evaluate the source run's metric_set against its final reference."""
    source_kind = reeval.REEVAL_SOURCE_KIND[plan.kind]
    reference = reeval.REEVAL_REFERENCE[plan.kind]
    source = queries.get_run_plan(session, source_kind, plan.target_date)
    if source is None or source.run_id is None:
        queries.mark_plan_failed(
            session,
            plan,
            error="plan fuente sin run",
            retry_at=timeutil.retry_due(now, config),
        )
        return
    run = queries.get_run(session, source.run_id)
    if run is None:
        raise ValueError(f"plan fuente {source_kind} sin run {source.run_id}")
    reeval.reevaluate_metrics(session, run, reference=reference, data_dir=data_dir)
    queries.mark_plan_done(session, plan)
