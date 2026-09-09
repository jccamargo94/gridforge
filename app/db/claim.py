"""Postgres-only locking lives here, and only here: `FOR UPDATE SKIP LOCKED`
is what lets more than one worker replica claim rows safely without
stepping on each other. SQLite's dialect doesn't support that clause at
all, so on SQLite (tests, single process) it's simply never added --
there's nothing broken by its absence since SQLite doesn't run concurrent
worker replicas anyway."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Run, RunPlan


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
