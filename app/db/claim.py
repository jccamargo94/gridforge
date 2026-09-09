"""Postgres-only locking lives here, and only here: `FOR UPDATE SKIP LOCKED`
is what lets more than one worker replica claim rows safely without
stepping on each other. SQLite's dialect doesn't support that clause at
all, so on SQLite (tests, single process) it's simply never added --
there's nothing broken by its absence since SQLite doesn't run concurrent
worker replicas anyway."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import queries
from app.db.models import Run, RunPlan

PLAN_STALE_ERROR = "worker reiniciado con plan en running (stale)"
RUN_STALE_ERROR = "run interrumpido por reinicio del worker (stale)"


def _locked(stmt, session: Session):
    """Apply the postgres-only row lock; unchanged on every other dialect."""
    if session.bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)
    return stmt


def claim_next_pending_run(session: Session) -> Run | None:
    stmt = select(Run).where(Run.status == "pending").order_by(Run.created_at).limit(1)
    run = session.scalars(_locked(stmt, session)).first()
    if run is None:
        return None
    run.status = "running"
    run.started_at = datetime.now(timezone.utc)
    session.commit()
    return run


def claim_run_by_id(session: Session, run_id: str) -> Run | None:
    """Claim one specific pending run (used by the plan executor right after
    creating it). Returns None if another worker claimed it first."""
    stmt = select(Run).where(Run.id == run_id, Run.status == "pending")
    run = session.scalars(_locked(stmt, session)).first()
    if run is None:
        return None
    run.status = "running"
    run.started_at = datetime.now(timezone.utc)
    session.commit()
    return run


def claim_run_plan_by_id(session: Session, plan_id: str) -> RunPlan | None:
    """Claim one run_plans row for execution.

    pending rows are claimable; failed rows are re-claimable (retry). The
    caller only lists failed rows whose attempts are below the max, and the
    attempt counter increments on every claim (one claim == one attempt).
    """
    stmt = select(RunPlan).where(RunPlan.id == plan_id, RunPlan.status.in_(["pending", "failed"]))
    plan = session.scalars(_locked(stmt, session)).first()
    if plan is None:
        return None
    plan.status = "running"
    plan.started_at = datetime.now(timezone.utc)
    plan.attempts += 1
    session.commit()
    return plan


def reconcile_stale_running(session: Session, *, now: datetime) -> tuple[int, int]:
    """Reconcile rows left `running` by a crashed worker; call ONCE at boot.

    Single-process-worker assumption: at boot no live worker owns these rows,
    so marking them failed is not a steal. Multi-worker deployments need an
    age-based reaper instead (out of scope).

    Plans: every stale `running` plan becomes `failed` with the stale marker
    and retry scheduled at `now`, mirroring `queries.mark_plan_failed`'s
    mark-vs-retry semantics (attempts were already incremented at claim).
    Rows below the attempt cap are claimable again — the next plan tick
    decides by window (open -> retry, expired -> honest skip); rows at/above
    the cap are never listed again, so they stay terminal in effect.
    Runs: every stale `running` run becomes `failed` with the interruption
    marker and `finished_at = now`.

    Returns (plans_reconciled, runs_reconciled).
    """
    plans = list(session.scalars(select(RunPlan).where(RunPlan.status == "running")))
    for plan in plans:
        queries.mark_plan_failed(session, plan, error=PLAN_STALE_ERROR, retry_at=now)
    runs = list(session.scalars(select(Run).where(Run.status == "running")))
    for run in runs:
        run.status = "failed"
        run.error = RUN_STALE_ERROR
        run.finished_at = now
        session.add(run)
    session.commit()
    return len(plans), len(runs)
