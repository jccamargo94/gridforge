"""Plan-row creation: daily lanes, TX1 sweep, monthly settled gate.

Creation is event-driven but idempotent: rows are created once per
(kind, target_date) (schema UNIQUE) and then live through the claim/retry/
expiry machine of tick.py. The sweep lookback is a code constant, not env
config: TX1 dates older than ~7 days predate this feature and would flood
the worker with a historical backfill on first deploy.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from app.db import queries
from app.scheduler import inputs, timeutil

_SWEEP_LOOKBACK_DAYS = 7

KIND_LEVEL = {
    "preideal_daily": "preideal",
    "ideal_daily": "ideal",
    "preideal_settled": "preideal",
    "ideal_settled": "ideal",
    "lmp_settled": "lmp",
}

KIND_INPUT_GRADE = {
    "preideal_daily": "provisional",
    "ideal_daily": "provisional",
    "preideal_settled": "settled",
    "ideal_settled": "settled",
    "lmp_settled": "settled",
}

_DAILY_KINDS = ("preideal_daily", "ideal_daily", "reeval_preideal")


def ensure_daily_plans(session, *, now: datetime, config) -> int:
    """Create tomorrow's daily + reeval_preideal rows if missing."""
    if not config.daily_enabled:
        return 0
    target = timeutil.tz_date(now, config.scheduler_tz) + timedelta(days=1)
    created = 0
    for kind in _DAILY_KINDS:
        if queries.get_run_plan(session, kind, target) is not None:
            continue
        open_at, _close = timeutil.window_edges(kind, target, config)
        due_at = now if open_at is None or now > open_at else open_at
        queries.create_run_plan(session, kind=kind, target_date=target, due_at=due_at)
        created += 1
    return created


def sweep_create_rows(session, *, now: datetime, config, data_dir: str) -> int:
    """Create lmp_settled/reeval_ideal rows for TX1 dates; heal reeval_preideal.

    Called at/after SWEEP_TIME once per Bogota day (worker wiring decides).
    Only dates inside the last _SWEEP_LOOKBACK_DAYS Bogota days are considered
    (TX1 publishes D+2..D+4, so a fresh date is never dropped).
    """
    if not config.daily_enabled:
        return 0
    created = 0
    today = timeutil.tz_date(now, config.scheduler_tz)
    for offset in range(1, _SWEEP_LOOKBACK_DAYS + 1):
        day = today - timedelta(days=offset)
        has_tx1 = inputs.series_has_day("precio_bolsa", day, data_dir)
        if has_tx1:
            for kind in ("lmp_settled", "reeval_ideal"):
                if queries.get_run_plan(session, kind, day) is None:
                    queries.create_run_plan(session, kind=kind, target_date=day, due_at=now)
                    created += 1
        if queries.get_run_plan(session, "reeval_preideal", day) is None and inputs.source_run_done(
            session, "preideal_daily", day
        ):
            queries.create_run_plan(session, kind="reeval_preideal", target_date=day, due_at=now)
            created += 1
    return created


def _month_days(month_start: date) -> list[date]:
    if month_start.month == 12:
        end = date(month_start.year + 1, 1, 1)
    else:
        end = date(month_start.year, month_start.month + 1, 1)
    return [month_start + timedelta(days=i) for i in range((end - month_start).days)]


def create_settled_rows_for_month(session, *, month_start: date, config, due_at: datetime) -> int:
    """Create preideal_settled/ideal_settled rows for every day of the month."""
    if not config.daily_enabled:
        return 0
    created = 0
    for day in _month_days(month_start):
        for kind in ("preideal_settled", "ideal_settled"):
            if queries.get_run_plan(session, kind, day) is None:
                queries.create_run_plan(session, kind=kind, target_date=day, due_at=due_at)
                created += 1
    return created


def next_settlement_month(session, *, now: datetime, config, data_dir: str) -> date | None:
    """Most recent complete calendar month before the current Bogota month.

    A month publishes ~1st of the next month; the gate fires after the pull
    that completes it. Only months strictly before the current one count.
    """
    today = timeutil.tz_date(now, config.scheduler_tz)
    first = date(today.year, today.month, 1) - timedelta(days=1)  # last day of prev month
    cursor = date(first.year, first.month, 1)
    while cursor >= date(today.year - 1, 1, 1):
        if inputs.month_complete("ofertas", cursor, data_dir):
            return cursor
        cursor = (
            date(cursor.year - 1, 12, 1)
            if cursor.month == 1
            else date(cursor.year, cursor.month - 1, 1)
        )
    return None
