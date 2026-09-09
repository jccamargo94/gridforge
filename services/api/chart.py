"""GET /chart/series builder (spec section 7.1): one row per Bogota calendar
day with the daily mean (COP/MWh) of five series. Simulated series come from
public done runs; externals come from the year CSVs / per-date iMAR."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from app.data.actuals import load_actual_bolsa, load_actual_price
from app.db import queries
from app.storage import get_storage

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


def _mean_price(run, day: date) -> float | None:
    if run.price_path is None:
        return None
    try:
        with get_storage(".").open(run.price_path) as f:
            df = pd.read_csv(f, parse_dates=["datetime"])
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return None
    sub = df[df["datetime"].dt.date == day]["ideal_marginal_price"]
    if sub.empty:
        return None
    return float(sub.astype(float).mean())


def _mean_actual(fn, day: date, data_dir: str) -> float | None:
    try:
        values = fn(day, data_dir=data_dir)
    except (FileNotFoundError, ValueError):
        return None
    if len(values) == 0:
        return None
    return float(sum(values) / len(values))


def build_chart_series(session, *, days: int, today: date, data_dir: str = "data") -> list[dict]:
    """Rows for the last `days` calendar days ending at `today` (inclusive)."""
    candidates: dict[tuple[date, str], tuple] = {}
    for run, case in queries.list_done_public_dispatch_runs(session):
        key = (case.level, run.input_grade)
        slot = _LEVEL_KEYS.get(key)
        if slot is None:
            continue
        # query orders created_at desc -> first hit per (date, slot) is newest
        candidates.setdefault((case.dispatch_date, slot), (run, case))

    rows = []
    start = today - timedelta(days=days - 1)
    for offset in range(days):
        day = start + timedelta(days=offset)
        row: dict = {"date": day.isoformat()}
        row["bolsa_tx1"] = _mean_actual(load_actual_bolsa, day, data_dir)
        row["mpo_xm"] = _mean_actual(load_actual_price, day, data_dir)
        for chart_key, slot_keys in _SERIES_KEYS.items():
            value = None
            run_id = None
            for slot in slot_keys:
                hit = candidates.get((day, _LEVEL_KEYS[slot]))
                if hit is not None:
                    run, _case = hit
                    value = _mean_price(run, day)
                    run_id = run.id
                    break
            row[chart_key] = value
            row[f"{chart_key}_run_id"] = run_id
        rows.append(row)
    return rows
