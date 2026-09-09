"""The plan tick: windows -> inputs -> claim -> execute (one plan per pass).

Policy documented for the orchestrator (plan Notes): at most one plan per
tick because a plan run solves inline and blocks the worker loop; the loop
re-enters every PLAN_TICK_SECONDS. Windowed kinds that age out while the
worker is down become `skipped` with reason "ventana vencida" on the first
tick after wake (auditable evidence, spec section 3.1). Open-ended kinds
never expire on time — deterministic input failures skip them via the
`permanent` path from inputs.kind_inputs_ready.
"""

from __future__ import annotations

from datetime import datetime

from app.db import queries
from app.db.claim import claim_run_plan_by_id
from app.scheduler import executor, inputs, reeval, timeutil
from app.scheduler.plans import ensure_daily_plans

# Closed kind set of spec section 4. window_edges fails open for unknown
# kinds (returns an unbounded window), so the tick validates the kind itself
# before consulting it: a row with an unknown kind must never be silently
# claimable forever — it is skipped with a recorded reason (fail-closed,
# auditable).
_KNOWN_KINDS = frozenset(
    (
        "preideal_daily",
        "ideal_daily",
        "reeval_preideal",
        "reeval_ideal",
        "lmp_settled",
        "preideal_settled",
        "ideal_settled",
    )
)

REASON_UNKNOWN_KIND = "kind desconocido"
REASON_WINDOW_EXPIRED = "ventana vencida"


def plan_tick(
    session,
    *,
    now: datetime,
    config,
    data_dir: str = "data",
    results_root: str = "data/results",
) -> int:
    """One plan-tick pass; executes at most one plan. Returns 1 when it did."""
    if not config.daily_enabled:
        return 0
    ensure_daily_plans(session, now=now, config=config)

    for plan in queries.list_claimable_plans(
        session, now=now, max_attempts=config.plan_max_attempts
    ):
        if plan.kind not in _KNOWN_KINDS:
            queries.mark_plan_skipped(session, plan, reason=REASON_UNKNOWN_KIND)
            continue
        open_at, close_at = timeutil.window_edges(plan.kind, plan.target_date, config)
        if close_at is not None and now > close_at:
            if plan.attempts == 0:
                # Never attempted: an honest skip keeps the audit trail clean.
                queries.mark_plan_skipped(session, plan, reason=REASON_WINDOW_EXPIRED)
            else:
                # It ran and failed (attempts > 0): terminal failure, not a
                # skip — mark_plan_skipped would erase the retry history. The
                # window is gone so there is no retry_at: finished_at stamps
                # the row terminal and list_claimable_plans drops it.
                queries.mark_plan_failed(
                    session, plan, error=plan.error or "ventana vencida tras reintentos"
                )
            continue
        if open_at is not None and now < open_at:
            continue

        ready, reason, permanent = inputs.kind_inputs_ready(
            session, plan.kind, plan.target_date, data_dir=data_dir
        )
        if not ready:
            if permanent:
                queries.mark_plan_skipped(session, plan, reason=reason)
            continue

        claimed = claim_run_plan_by_id(session, plan.id)
        if claimed is None:
            continue  # another replica claimed it first
        try:
            if claimed.kind in reeval.REEVAL_SOURCE_KIND:
                executor.execute_reeval(session, claimed, now=now, config=config, data_dir=data_dir)
            else:
                executor.execute_plan(
                    session,
                    claimed,
                    now=now,
                    config=config,
                    data_dir=data_dir,
                    results_root=results_root,
                )
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            if claimed.attempts >= config.plan_max_attempts:
                queries.mark_plan_failed(session, claimed, error=error)
            else:
                queries.mark_plan_failed(
                    session,
                    claimed,
                    error=error,
                    retry_at=timeutil.retry_due(now, config),
                )
        return 1
    return 0
