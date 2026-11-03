"""Estimate the daily additive term (dI) of XM's spot price and report the
price error with it removed.

CREG 051/2009 and 011/2010 define the bolsa price as the offer of the last
non-inflexible plant needed (MPO) plus a daily "valor adicional" (dI). The
model reproduces the MPO but has no dI, so part of its error against the real
bolsa price is just the missing dI. On 7 real days, 166 of 168 hours had an
available unit whose offer equals (real price - dI) for a per-day constant dI
of 0-22k COP/MWh, versus 76 of 168 hours with dI = 0.

How it is estimated (an inference, not a published number): among candidate
shifts s in [0, max_delta) -- 0 plus the gaps between each hour's real price
and the available offers below it -- pick the s that makes the most hours'
(price - s) coincide (relative tolerance `tol`) with the offer of a unit
declared available in that hour; ties keep the smaller s. The count of matched
hours is returned so callers can ignore a poor fit.

Units: ofertas.Value is COP/kWh -> x1e3 to COP/MWh (same as case_builder.py);
the spot price is already COP/MWh (loaders.load_precio_bolsa scales it).
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from app.data import actuals, loaders
from app.utils.metrics import price_metrics

MATCH_TOL = 0.003
MAX_DELTA = 30_000.0
MIN_MATCHED_HOURS = 18


def estimate_delta_i(
    spot: np.ndarray,
    offers: pd.Series,
    available: list[set[str]],
    *,
    tol: float = MATCH_TOL,
    max_delta: float = MAX_DELTA,
) -> tuple[float, int]:
    """`spot`: 24 prices (COP/MWh); `offers`: resource -> COP/MWh for the day;
    `available`: for each hour, the set of resources declared available."""
    per_hour = [
        np.sort(offers[offers.index.isin(available[h])].to_numpy(dtype=float))
        for h in range(len(spot))
    ]
    candidates = {0.0}
    for h, offs in enumerate(per_hour):
        for o in offs:
            gap = spot[h] - o
            if 0 < gap < max_delta:
                candidates.add(round(float(gap), 0))

    def matched(shift: float) -> int:
        return sum(
            bool(len(offs)) and bool(np.any(np.abs(offs - (spot[h] - shift)) <= tol * spot[h]))
            for h, offs in enumerate(per_hour)
        )

    best = max(sorted(candidates), key=lambda s: (matched(s), -s))
    return best, matched(best)


def delta_i_metrics(
    dispatch_date: date, y_true, y_pred, *, data_dir: str = "data"
) -> dict[str, float]:
    """Extra metrics for ideal/lmp runs scored against the real bolsa price.

    Returns {} when the real bolsa price or the day's offers are missing, when
    `y_true` is not that bolsa price (e.g. an iMAR fallback), or when too few
    hours match an offer for the dI to be trusted (< MIN_MATCHED_HOURS).
    """
    try:
        spot = actuals.load_actual_bolsa(dispatch_date, data_dir=data_dir)
        ofertas = loaders.load_ofertas(data_dir, dispatch_date.year)
        dispo = loaders.load_dispo(data_dir, dispatch_date.year)
    except (FileNotFoundError, ValueError):
        return {}
    y_true = np.asarray(y_true, dtype=float)
    if len(spot) != 24 or len(y_true) < 24 or not np.allclose(y_true[:24], spot, rtol=1e-9):
        return {}

    day_offers = ofertas[ofertas["Date"].dt.date == dispatch_date]
    if day_offers.empty:
        return {}
    offers = (
        day_offers.drop_duplicates("resource_name", keep="last")
        .set_index("resource_name")["Value"]
        .astype(float)
        * 1e3
    )
    day_dispo = dispo[(dispo["datetime"].dt.date == dispatch_date) & (dispo["dispo"] > 0)]
    hours = day_dispo["datetime"].dt.hour
    available = [set(day_dispo.loc[hours == h, "resource_name"].dropna()) for h in range(24)]

    delta, n_matched = estimate_delta_i(spot, offers, available)
    if n_matched < MIN_MATCHED_HOURS:
        return {}
    n = min(len(y_true), len(y_pred))
    ex = price_metrics(y_true[:n] - delta, np.asarray(y_pred, dtype=float)[:n])
    out = {"delta_i": float(delta), "delta_i_hours_matched": float(n_matched)}
    out.update(
        {f"{k}_ex_delta": float(v) for k, v in ex.items() if k in ("rmse", "mae", "bias", "wape")}
    )
    return out
