"""Freshness tick: windowed incremental pull of the five real XM series,
keyed merge into the year CSVs, loader-cache invalidation, then the monthly
settled gate.

Pull-range policy (plan Notes, resolving spec section 5.1): a fixed 7-day
window can never capture a month that XM publishes as a single block ~1st
of the next month (spec section 1: PrecOferDesp). The request therefore
starts at min(today - DATA_REFRESH_WINDOW_DAYS, last_local_day + 1), i.e.
always at least the window back AND reaching back to the day after the last
locally merged row — the closed month arrives whole on the first pull after
publication, with no separate monthly job.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.data import loaders, xm_bulk
from app.data.heuristic.biddings import prune_estimated_rows
from app.data.xm_bulk import (
    refresh_dema_come,
    refresh_dispo_come,
    refresh_dispo_declarada,
    refresh_ofertas,
    refresh_precio_bolsa,
)
from app.scheduler import inputs, plans, timeutil

_SERIES = (
    ("dispo_declarada", refresh_dispo_declarada, True),
    ("ofertas", refresh_ofertas, True),
    ("demaCome", refresh_dema_come, False),
    ("dispo_come", refresh_dispo_come, True),
    ("precio_bolsa", refresh_precio_bolsa, False),
)


def _pull_start(name: str, end_day: date, config, data_dir: str) -> date:
    window_edge = end_day - timedelta(days=config.data_refresh_window_days)
    last = inputs.series_max_date(name, end_day.year, data_dir)
    if last is None:
        return window_edge
    return min(window_edge, last + timedelta(days=1))


def _year_segments(start: date, end: date) -> list[tuple[date, date]]:
    segments = []
    cursor = start
    while cursor <= end:
        seg_end = min(end, date(cursor.year, 12, 31))
        segments.append((cursor, seg_end))
        cursor = date(cursor.year + 1, 1, 1)
    return segments


def refresh_tick(session, *, now, config, data_dir: str = "data", consult=None) -> int:
    """One freshness pass. Returns settled rows created by the monthly gate."""
    if not config.daily_enabled:
        return 0
    from pydataxm.pydataxm import ReadDB

    consult_obj = consult if consult is not None else ReadDB()
    end_day = timeutil.tz_date(now, config.scheduler_tz) - timedelta(days=1)

    needs_crosswalk = any(needs for _, _, needs in _SERIES)
    crosswalk = xm_bulk.fetch_resource_crosswalk(consult_obj) if needs_crosswalk else None

    for name, refresh_fn, uses_crosswalk in _SERIES:
        start = _pull_start(name, end_day, config, data_dir)
        for seg_start, seg_end in _year_segments(start, end_day):
            refresh_fn(
                seg_start,
                seg_end,
                data_dir,
                consult_obj,
                crosswalk if uses_crosswalk else None,
                session=session,
            )
    loaders.clear_loader_caches()

    month = plans.next_settlement_month(session, now=now, config=config, data_dir=data_dir)
    if month is None:
        return 0
    created = plans.create_settled_rows_for_month(
        session, month_start=month, config=config, due_at=now
    )
    # Monthly gate = rolling-estimate pruning point (Wave-0 minor #4): the
    # real block now covers (Date, resource) pairs that previously only had
    # estimated rows; those same-date estimates are stale and must not keep
    # being served or rolled forward.
    prune_estimated_rows(
        data_dir, month_start=month, oferta_full=loaders.load_ofertas(data_dir, month.year)
    )
    return created
