from datetime import date as date_
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import Case, InputDataset, MetricSet, NodalResult, Run, RunPlan, Scenario
from app.schemas import BessScenario, NodalRunResult, RunResult


def create_scenario(session: Session, scenario: BessScenario, created_by: str) -> Scenario:
    row = Scenario(
        mode=scenario.mode.value,
        penetration_level=scenario.penetration_level,
        units=[u.model_dump() for u in scenario.units],
        created_by=created_by,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def get_scenario(session: Session, scenario_id: str) -> Scenario | None:
    return session.get(Scenario, scenario_id)


def list_scenarios(session: Session) -> list[Scenario]:
    stmt = select(Scenario).order_by(Scenario.created_at.desc())
    return list(session.scalars(stmt))


def create_case_and_run(
    session: Session,
    *,
    dispatch_date: date_,
    level: str,
    solver: str,
    compute_prices: bool,
    scenario_id: str | None,
    user_id: str | None = None,
    nodal_network: dict | None = None,
    visibility: str = "private",
    input_grade: str | None = None,
) -> Run:
    case = Case(
        dispatch_date=dispatch_date,
        level=level,
        solver=solver,
        compute_prices=compute_prices,
        scenario_id=scenario_id,
        nodal_network=nodal_network,
    )
    session.add(case)
    session.flush()  # populate case.id before Run references it

    run = Run(
        case_id=case.id,
        user_id=user_id,
        status="pending",
        visibility=visibility,
        input_grade=input_grade,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def get_run(session: Session, run_id: str) -> Run | None:
    return session.get(Run, run_id)


def get_case(session: Session, case_id: str) -> Case | None:
    return session.get(Case, case_id)


def list_runs_for_user(session: Session, user_id: str) -> list[Run]:
    stmt = select(Run).where(Run.user_id == user_id).order_by(Run.created_at.desc())
    return list(session.scalars(stmt))


def get_metric_set(session: Session, run_id: str) -> MetricSet | None:
    stmt = select(MetricSet).where(MetricSet.run_id == run_id)
    return session.scalars(stmt).first()


def finish_run_ok(
    session: Session,
    run: Run,
    result: RunResult,
    out_dir: str,
    *,
    reference: str | None = None,
) -> None:
    run.status = "done"
    run.finished_at = datetime.now(timezone.utc)
    run.out_dir = out_dir
    run.dispatch_path = result.dispatch_path
    run.price_path = result.price_path
    run.bess_path = result.bess_path
    run.marginal_plants_path = result.marginal_plants_path
    session.add(run)

    if result.metrics is not None or result.bess_summary is not None:
        metrics = result.metrics or {}
        bess = result.bess_summary or {}
        session.add(
            MetricSet(
                run_id=run.id,
                rmse=metrics.get("rmse"),
                mae=metrics.get("mae"),
                bias=metrics.get("bias"),
                wape=metrics.get("wape"),
                smape=metrics.get("smape"),
                r2=metrics.get("r2"),
                bess_charge_mwh=bess.get("bess_charge_mwh"),
                bess_discharge_mwh=bess.get("bess_discharge_mwh"),
                bess_avg_soc_mwh=bess.get("bess_avg_soc_mwh"),
                bess_net_revenue=bess.get("bess_net_revenue"),
                dispatch_mae_mw=metrics.get("dispatch_mae_mw"),
                dispatch_rmse_mw=metrics.get("dispatch_rmse_mw"),
                reference=reference,
                evaluated_at=datetime.now(timezone.utc) if reference else None,
            )
        )
    session.commit()


def get_nodal_result(session: Session, run_id: str) -> NodalResult | None:
    stmt = select(NodalResult).where(NodalResult.run_id == run_id)
    return session.scalars(stmt).first()


def finish_nodal_run_ok(session: Session, run: Run, result: RunResult, out_dir: str) -> None:
    assert result.nodal is not None
    run.status = "done"
    run.finished_at = datetime.now(timezone.utc)
    run.out_dir = out_dir
    session.add(run)

    nodal: NodalRunResult | None = result.nodal
    session.add(
        NodalResult(
            run_id=run.id,
            metrics=nodal.metrics if nodal else None,
            redistribution=nodal.redistribution if nodal else None,
            gen_revenue_by_zone=nodal.gen_revenue_by_zone if nodal else None,
            network=nodal.network if nodal else None,
            lmp_path=nodal.lmp_path if nodal else None,
            dispatch_path=nodal.dispatch_path if nodal else None,
            branch_flows_path=nodal.branch_flows_path if nodal else None,
            settlement_status_quo_path=nodal.settlement_status_quo_path if nodal else None,
            settlement_lmp_path=nodal.settlement_lmp_path if nodal else None,
            comparison_path=nodal.comparison_path if nodal else None,
            summary_path=nodal.summary_path if nodal else None,
        )
    )
    session.commit()


def finish_run_failed(session: Session, run: Run, error: str, log_path: str | None = None) -> None:
    # Clear any aborted transaction before mutating `run`. A DB error inside
    # run_case (e.g. upsert_input_dataset hitting a missing table) leaves the
    # session in Postgres's "current transaction is aborted" state; without this
    # rollback the commit below would raise InFailedSqlTransaction and the worker
    # would never record the failure. rollback() expires uncommitted attribute
    # changes, so callers pass log_path in (applied after this rollback) instead
    # of relying on an in-memory `run.log_path = ...` made before the call.
    session.rollback()
    run.status = "failed"
    run.finished_at = datetime.now(timezone.utc)
    run.error = error
    if log_path is not None:
        run.log_path = log_path
    session.add(run)
    session.commit()


def upsert_input_dataset(
    session: Session,
    *,
    dataset: str,
    partition_key: str,
    source: str,
    checksum: str | None = None,
    row_count: int | None = None,
) -> InputDataset:
    stmt = select(InputDataset).where(
        InputDataset.dataset == dataset, InputDataset.partition_key == partition_key
    )
    existing = session.scalars(stmt).first()
    if existing is not None:
        existing.source = source
        existing.checksum = checksum
        existing.row_count = row_count
        existing.fetched_at = datetime.now(timezone.utc)
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing

    row = InputDataset(
        dataset=dataset,
        partition_key=partition_key,
        source=source,
        checksum=checksum,
        row_count=row_count,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def get_input_dataset(session: Session, dataset: str, partition_key: str) -> InputDataset | None:
    stmt = select(InputDataset).where(
        InputDataset.dataset == dataset, InputDataset.partition_key == partition_key
    )
    return session.scalars(stmt).first()


def update_metric_set(
    session: Session, run_id: str, *, metrics: dict[str, float], reference: str
) -> MetricSet:
    """Overwrite a run's price metrics against an explicit reference.

    Keeps the dispatch columns (dispatch_mae_mw/dispatch_rmse_mw) untouched —
    they need the solved model, which post-hoc re-evaluation does not have.
    """
    ms = get_metric_set(session, run_id)
    if ms is None:
        ms = MetricSet(run_id=run_id)
    ms.rmse = metrics.get("rmse")
    ms.mae = metrics.get("mae")
    ms.bias = metrics.get("bias")
    ms.wape = metrics.get("wape")
    ms.smape = metrics.get("smape")
    ms.r2 = metrics.get("r2")
    ms.reference = reference
    ms.evaluated_at = datetime.now(timezone.utc)
    session.add(ms)
    session.commit()
    session.refresh(ms)
    return ms


def list_visible_runs(session: Session, user_id: str) -> list[Run]:
    stmt = (
        select(Run)
        .where(or_(Run.user_id == user_id, Run.visibility == "public"))
        .order_by(Run.created_at.desc())
    )
    return list(session.scalars(stmt))


def create_run_plan(
    session: Session, *, kind: str, target_date: date_, due_at: datetime
) -> RunPlan:
    row = RunPlan(kind=kind, target_date=target_date, due_at=due_at)
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def get_run_plan(session: Session, kind: str, target_date: date_) -> RunPlan | None:
    stmt = select(RunPlan).where(RunPlan.kind == kind, RunPlan.target_date == target_date)
    return session.scalars(stmt).first()


def list_claimable_plans(session: Session, *, now: datetime, max_attempts: int) -> list[RunPlan]:
    # finished_at IS NULL excludes terminal failures (marked failed with no
    # retry scheduled): only pending and retry-scheduled failed plans are
    # claimable again.
    stmt = (
        select(RunPlan)
        .where(
            RunPlan.due_at <= now,
            RunPlan.status.in_(["pending", "failed"]),
            RunPlan.finished_at.is_(None),
            or_(RunPlan.status == "pending", RunPlan.attempts < max_attempts),
        )
        .order_by(RunPlan.due_at, RunPlan.created_at)
    )
    return list(session.scalars(stmt))


def mark_plan_done(session: Session, plan: RunPlan, *, run_id: str | None = None) -> None:
    plan.status = "done"
    plan.run_id = run_id
    plan.finished_at = datetime.now(timezone.utc)
    session.add(plan)
    session.commit()


def mark_plan_failed(
    session: Session,
    plan: RunPlan,
    *,
    error: str,
    run_id: str | None = None,
    retry_at: datetime | None = None,
) -> None:
    plan.status = "failed"
    plan.error = error
    if run_id is not None:
        plan.run_id = run_id
    if retry_at is not None:
        plan.due_at = retry_at
    else:
        plan.finished_at = datetime.now(timezone.utc)
    session.add(plan)
    session.commit()
    if retry_at is not None:
        # SQLite stores DateTime(timezone=True) without the offset and commit()
        # reloads the row, so due_at would come back naive. Re-set the in-memory
        # value so callers comparing against the tz-aware retry instant (repo
        # pattern: timestamps tz-aware UTC) don't see a bare datetime.
        plan.due_at = retry_at


def mark_plan_skipped(session: Session, plan: RunPlan, *, reason: str) -> None:
    plan.status = "skipped"
    plan.error = reason
    plan.finished_at = datetime.now(timezone.utc)
    session.add(plan)
    session.commit()


def list_done_public_dispatch_runs(session: Session) -> list[tuple[Run, Case]]:
    """Public done runs of the dispatch levels the chart series consumes."""
    stmt = (
        select(Run, Case)
        .join(Case, Run.case_id == Case.id)
        .where(
            Run.visibility == "public",
            Run.status == "done",
            Case.level.in_(["preideal", "ideal"]),
        )
        .order_by(Run.created_at.desc())
    )
    return list(session.execute(stmt))
