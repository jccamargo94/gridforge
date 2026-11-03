"""Audit an offer against the agent's OWN offer history (issue #83).

Descriptive statistics only: no dispatch model, no recommendation of what to
offer (that is the market-power problem #79 fences off). The question
answered is "is this offer consistent with what this resource normally
offers?".

Data granularity: PrecOferDesp is ONE price per resource per day (see
app/data/xm_bulk.py::refresh_ofertas, which keeps only Values_Hour01), so the
band is per resource, optionally per weekday -- there is no hourly offer in
this dataset, whatever the issue text says.

Units: ofertas.csv `Value` is COP/kWh; this module converts to COP/MWh (x1e3,
the same factor case_builder.py applies) so it matches the rest of the API.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

MIN_HISTORY = 5
MIN_WEEKDAY_HISTORY = 4
WARN_Z = 2.0
ALERT_Z = 3.0
# With a constant history the std is 0 and z is undefined; any move beyond this
# relative tolerance is reported as a change instead of a z-score.
FLAT_TOLERANCE = 0.005


def _flag(price: float, hist: np.ndarray) -> tuple[str, float | None]:
    mean, std = float(hist.mean()), float(hist.std(ddof=1)) if len(hist) > 1 else 0.0
    if std == 0.0:
        moved = abs(price - mean) > FLAT_TOLERANCE * max(abs(mean), 1e-9)
        return ("changed" if moved else "ok"), None
    z = (price - mean) / std
    if abs(z) >= ALERT_Z:
        return "alert", z
    if abs(z) >= WARN_Z:
        return "warn", z
    return "ok", z


def audit_offer(
    history: pd.DataFrame,
    resource: str,
    day: date,
    price_cop_mwh: float | None,
    window_days: int = 90,
) -> dict:
    """`history`: ofertas rows (Date, resource_name, Value COP/kWh), any span.
    `price_cop_mwh=None` audits the offer already published for `day`."""
    h = history[history["resource_name"] == resource].copy()
    h["day"] = h["Date"].dt.date
    h["price"] = h["Value"].astype(float) * 1e3
    h = h.drop_duplicates("day", keep="last")

    published = h.loc[h["day"] == day, "price"]
    if price_cop_mwh is None:
        if published.empty:
            return {"resource": resource, "date": day.isoformat(), "status": "no_offer"}
        price = float(published.iloc[0])
        source = "published"
    else:
        price = float(price_cop_mwh)
        source = "candidate"

    start = day - timedelta(days=window_days)
    past = h[(h["day"] < day) & (h["day"] >= start)].sort_values("day")
    out: dict = {
        "resource": resource,
        "date": day.isoformat(),
        "price_cop_mwh": round(price, 3),
        "price_source": source,
        "window_days": window_days,
        "n_history": int(len(past)),
    }
    if len(past) < MIN_HISTORY:
        return {**out, "status": "insufficient_history", "flag": None}

    vals = past["price"].to_numpy()
    flag, z = _flag(price, vals)
    last = float(vals[-1])
    same_dow = past[pd.to_datetime(past["day"]).dt.dayofweek == day.weekday()]["price"].to_numpy()
    dow = None
    if len(same_dow) >= MIN_WEEKDAY_HISTORY:
        dow_flag, dow_z = _flag(price, same_dow)
        dow = {
            "n": int(len(same_dow)),
            "mean_cop_mwh": round(float(same_dow.mean()), 3),
            "flag": dow_flag,
            "z": None if dow_z is None else round(dow_z, 3),
        }
    return {
        **out,
        "status": "ok",
        "flag": flag,
        "z": None if z is None else round(z, 3),
        "band": {
            "mean_cop_mwh": round(float(vals.mean()), 3),
            "std_cop_mwh": round(float(vals.std(ddof=1)), 3),
            "p05_cop_mwh": round(float(np.percentile(vals, 5)), 3),
            "p50_cop_mwh": round(float(np.percentile(vals, 50)), 3),
            "p95_cop_mwh": round(float(np.percentile(vals, 95)), 3),
            "min_cop_mwh": round(float(vals.min()), 3),
            "max_cop_mwh": round(float(vals.max()), 3),
        },
        "percentile_rank": round(float((vals <= price).mean() * 100), 1),
        "last_offer_cop_mwh": round(last, 3),
        "change_vs_last_pct": round((price - last) / last * 100, 2) if last else None,
        "same_weekday": dow,
    }
