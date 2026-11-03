"""Daily scheduler: enqueue the core runs (ideal/preideal) for the latest day.

It only *creates* `pending` runs; the worker's existing polling loop executes
them. Each call is idempotent per (date, level): safe to call every minute, from
several worker replicas, and alongside manually created runs.

Policy (all overridable through env vars, see `SchedulerConfig.from_env`):
- Target date = today (Colombia, UTC-5, no DST) minus `lag_days` (default 1: XM
  publishes the ex-post inputs the day after).
- Nothing is enqueued before `hour` local time.
- A (date, level) that already has a pending/running/done run (manual or
  scheduled) is skipped: no re-runs of finished work.
- If only failed runs exist, retry every `retry_minutes` up to `max_attempts`
  *scheduled* attempts. That covers XM publishing inputs late. After that the
  failed runs stay visible in the runs list instead of being retried forever.
"""

import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import queries
from app.db.models import Run

SYSTEM_USER_ID = "system:scheduler"
COLOMBIA_TZ = timezone(timedelta(hours=-5))
_ADVISORY_LOCK_KEY = 8_901_001
_ACTIVE_OR_DONE = {"pending", "running", "done"}


@dataclass(frozen=True)
class SchedulerConfig:
    enabled: bool = False
    levels: tuple[str, ...] = ("ideal", "preideal")
    hour: int = 6
    lag_days: int = 1
    max_attempts: int = 3
    retry_minutes: int = 60
    solver: str = "cbc"

    @classmethod
    def from_env(cls, env=os.environ) -> "SchedulerConfig":
        defaults = cls()
        levels = tuple(
            lv.strip() for lv in env.get("DAILY_RUN_LEVELS", "").split(",") if lv.strip()
        )
        return cls(
            enabled=env.get("DAILY_SCHEDULER_ENABLED", "").lower() in {"1", "true", "yes"},
            levels=levels or defaults.levels,
            hour=int(env.get("DAILY_RUN_HOUR", defaults.hour)),
            lag_days=int(env.get("DAILY_RUN_LAG_DAYS", defaults.lag_days)),
            max_attempts=int(env.get("DAILY_RUN_MAX_ATTEMPTS", defaults.max_attempts)),
            retry_minutes=int(env.get("DAILY_RUN_RETRY_MINUTES", defaults.retry_minutes)),
            solver=env.get("DAILY_RUN_SOLVER", defaults.solver),
        )


def target_date(now: datetime, cfg: SchedulerConfig) -> date:
    return now.astimezone(COLOMBIA_TZ).date() - timedelta(days=cfg.lag_days)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _should_enqueue(runs: list[Run], now: datetime, cfg: SchedulerConfig) -> bool:
    if any(r.status in _ACTIVE_OR_DONE for r in runs):
        return False
    scheduled_failures = [r for r in runs if r.source == "scheduled"]
    if len(scheduled_failures) >= cfg.max_attempts:
        return False
    if scheduled_failures:
        last = max(_aware(r.finished_at or r.created_at) for r in scheduled_failures)
        if now - last < timedelta(minutes=cfg.retry_minutes):
            return False
    return True


def enqueue_daily_runs(session: Session, now: datetime, cfg: SchedulerConfig) -> list[Run]:
    """Create the pending runs due at `now`. Returns the runs created (maybe empty)."""
    if now.astimezone(COLOMBIA_TZ).hour < cfg.hour:
        return []

    if session.bind.dialect.name == "postgresql":
        # Transaction-scoped lock: serialises concurrent replicas so the
        # check-then-insert below can't create duplicate runs.
        session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _ADVISORY_LOCK_KEY})

    day = target_date(now, cfg)
    created: list[Run] = []
    for level in cfg.levels:
        runs = queries.list_runs_for_case_key(
            session, dispatch_date=day, level=level, solver=cfg.solver
        )
        if not _should_enqueue(runs, now, cfg):
            continue
        created.append(
            queries.create_case_and_run(
                session,
                dispatch_date=day,
                level=level,
                solver=cfg.solver,
                compute_prices=True,
                scenario_id=None,
                user_id=SYSTEM_USER_ID,
                source="scheduled",
            )
        )
    session.commit()  # release the advisory lock even when nothing was created
    for run in created:
        print(f"[scheduler] enqueued {run.source} run {run.id} for {day}", file=sys.stderr)
    return created
