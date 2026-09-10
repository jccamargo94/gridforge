"""GET /chart/series builder: one row per Bogota calendar day with the daily
mean (COP/MWh) plus a length-24 hourly array (null holes) for the five price
series served to the Home chart.

`hourly_series` is the single serving source (REQ-HC-01/02): externals come
from public rows (`source='xm'`); simulated series come from the winner
run's rows (`source = run id`), where the winner per (Bogota day, chart key)
is ranked runs-side over the caller's visible scope — (level, input_grade)
priority, then created_at desc (B2). Per-request CSV reads are gone.
"""

from __future__ import annotations

from datetime import date, timedelta, timezone
from typing import Sequence
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.db import queries, series

UTC = timezone.utc
BOGOTA = ZoneInfo("America/Bogota")

_LEVEL_KEYS = {
    ("ideal", "settled"): "ideal_settled",
    ("ideal", "provisional"): "ideal_provisional",
    ("preideal", "settled"): "preideal_settled",
    ("preideal", "provisional"): "preideal_daily",
}
# per simulated chart key: (level, input_grade) candidate list, best first
_SERIES_KEYS = {
    "ideal_settled": [("ideal", "settled")],
    "ideal_provisional": [("ideal", "provisional")],
    "preideal": [("preideal", "settled"), ("preideal", "provisional")],
}
_EXTERNAL_KEYS = ("bolsa_tx1", "mpo_xm")


def _bogota_dt(ts) -> tuple[date, int]:
    """(Bogota day, Bogota hour) of a stored ts (SQLite returns naive UTC)."""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    local = ts.astimezone(BOGOTA)
    return local.date(), local.hour


def _summary(
    items: Sequence[tuple[int, float]],
) -> tuple[float | None, list[float | None]]:
    """Daily mean of the day's rows + length-24 hourly array (null holes)."""
    hourly: list[float | None] = [None] * 24
    total = 0.0
    count = 0
    for hour, value in items:
        hourly[hour] = value
        total += value
        count += 1
    return (total / count) if count else None, hourly


def build_chart_series(
    session: Session, *, days: int, today: date, user_id: str | None = None
) -> list[dict]:
    """Rows for the last `days` Bogota calendar days ending at `today`
    (inclusive), scoped to the caller's tenant visibility."""
    tenant_ids = series.tenant_ids_for_user(session, user_id) if user_id else []
    start = today - timedelta(days=days - 1)

    # (bogota_day, series_key, source) -> [(bogota_hour, value)] across the
    # caller's visible scope; one pass over the table for the whole window
    hourly: dict[tuple[date, str, str], list[tuple[int, float]]] = {}
    for row in series.fetch_visible_rows(session, start=start, end=today, tenant_ids=tenant_ids):
        day, hour = _bogota_dt(row.ts)
        hourly.setdefault((day, row.series_key, row.source), []).append((hour, row.value))

    def _excerpt(day: date, key: str, source: str):
        return _summary(hourly.get((day, key, source), []))

    # runs-side winner per (dispatch day, slot): query orders created_at desc,
    # so the first hit per slot is the newest (grade priority comes from the
    # slot list itself in the per-key loop below)
    candidates: dict[tuple[date, str], tuple] = {}
    for run, case in queries.list_done_public_dispatch_runs(session, user_id=user_id):
        slot = _LEVEL_KEYS.get((case.level, run.input_grade))
        if slot is None:
            continue
        candidates.setdefault((case.dispatch_date, slot), (run, case))

    rows = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        row: dict = {"date": day.isoformat()}
        for key in _EXTERNAL_KEYS:
            value, hourly_values = _excerpt(day, key, series.XM_SOURCE)
            row[key] = value
            row[f"{key}_hourly"] = hourly_values
        for chart_key, slot_keys in _SERIES_KEYS.items():
            value = None
            run_id = None
            hourly_values = [None] * 24
            for slot in slot_keys:
                hit = candidates.get((day, _LEVEL_KEYS[slot]))
                if hit is not None:
                    run, _case = hit
                    value, hourly_values = _excerpt(day, series.RUN_SERIES_KEY, run.id)
                    # a winner whose rows are missing (e.g. unreadable
                    # price_path at finish) yields null and no run id (D3)
                    run_id = run.id if value is not None else None
                    break
            row[chart_key] = value
            row[f"{chart_key}_run_id"] = run_id
            row[f"{chart_key}_hourly"] = hourly_values
        rows.append(row)
    return rows
