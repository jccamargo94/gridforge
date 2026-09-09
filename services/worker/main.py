import time
import traceback
from dataclasses import dataclass
from datetime import date, datetime, timezone

from app.db.claim import claim_next_pending_run, reconcile_stale_running
from app.db.session import get_engine, get_sessionmaker
from app.scheduler import plans, refresh, tick, timeutil
from app.scheduler.config import SchedulerConfig
from app.scheduler.executor import execute_run

POLL_INTERVAL_SECONDS = 5


@dataclass
class WorkerState:
    plan_next: float = 0.0  # time.monotonic() deadlines
    fresh_next: float = 0.0
    last_sweep_date: date | None = None


def process_once(session, *, data_dir: str = "data", results_root: str = "data/results") -> bool:
    run = claim_next_pending_run(session)
    if run is None:
        return False
    execute_run(session, run, data_dir=data_dir, results_root=results_root)
    return True


def main_iteration(
    session,
    state: WorkerState | None = None,
    *,
    now: datetime | None = None,
    config: SchedulerConfig | None = None,
    data_dir: str = "data",
    results_root: str = "data/results",
) -> WorkerState:
    """One pass of the worker loop body. Scheduled ticks first (each isolated),
    then one manual-lane run. Never raises."""
    if state is None:
        state = WorkerState()
    now = now or datetime.now(timezone.utc)
    config = config or SchedulerConfig.from_env()

    if config.daily_enabled:
        # Refresh BEFORE plan (post-final-review amendment): a plan claim in
        # the same pass must observe the year-series rows and per-date blobs
        # fetched by that pass's freshness tick; sweep stays after plan, and
        # the manual lane stays last, outside the daily block.
        if time.monotonic() >= state.fresh_next:
            state.fresh_next = time.monotonic() + 60 * config.data_refresh_interval_minutes
            try:
                refresh.refresh_tick(session, now=now, config=config, data_dir=data_dir)
            except Exception:
                traceback.print_exc()
        if time.monotonic() >= state.plan_next:
            state.plan_next = time.monotonic() + config.plan_tick_seconds
            try:
                tick.plan_tick(
                    session,
                    now=now,
                    config=config,
                    data_dir=data_dir,
                    results_root=results_root,
                )
            except Exception:
                traceback.print_exc()
        fire, day = timeutil.sweep_due(now, config, state.last_sweep_date)
        if fire:
            state.last_sweep_date = day
            try:
                plans.sweep_create_rows(session, now=now, config=config, data_dir=data_dir)
            except Exception:
                traceback.print_exc()

    try:
        process_once(session, data_dir=data_dir, results_root=results_root)
    except Exception:
        traceback.print_exc()
    return state


def main() -> None:
    engine = get_engine()
    session_factory = get_sessionmaker(engine)
    # F2: rows left `running` by a crash are reconciled once at boot (stale
    # plans become retry-scheduled failures, stale runs terminal failures).
    with session_factory() as session:
        reconcile_stale_running(session, now=datetime.now(timezone.utc))
    state = WorkerState()
    while True:
        with session_factory() as session:
            try:
                state = main_iteration(session, state)
            except Exception:
                traceback.print_exc()
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
