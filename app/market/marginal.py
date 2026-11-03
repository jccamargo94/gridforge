"""Historical map of price-setting ("marginal") candidates (issue #86).

Observed data only: the actual spot price (PrecBolsNaci, `precio_bolsa`), the
daily offers (`ofertas`, PrecOferDesp) and the declared availability. No
dispatch model, no LMP.

Method. In a given hour a resource is a *candidate* to have set the price when
it was available (dispo > 0) and its offer is within `tol` (relative) of the
spot price. If k resources qualify, each gets weight 1/k, so a heatmap cell is
the expected fraction of days a technology/zone set the price at that hour.
Hours with no candidate are reported as unattributed.

Why not app/data/heuristic/biddings.py::detect_marginal_resources (which the
issue suggests reusing): it needs per-date PrId (dispatched MW) and iMAR files
that are downloaded one day at a time and are not part of the year CSVs, and it
resolves one hour per resource by elimination -- it cannot yield a per-hour
frequency over a long history. This module uses the year CSVs the product
already ingests; the two approaches are complementary, not equivalent.

Caveats (surfaced in the API): spot price = MPO + a (small) uplift term, so
`tol` must absorb it; ties between equal offers split the weight; a resource
without an offer that day can never be attributed.

Units: dispo/ofertas/precio_bolsa are brought to COP/MWh with the same factors
case_builder.py / loaders.py apply (ofertas Value COP/kWh x1e3; loaders scale
precio_bolsa x1e3). Only resource gen_type and (optionally) zone are returned,
never a resource name -- same privacy policy as app/market/merit.py.
"""

from __future__ import annotations

import re
import unicodedata

import pandas as pd


def normalize_name(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())


def marginal_map(
    dispo: pd.DataFrame,
    ofertas: pd.DataFrame,
    precio_bolsa: pd.DataFrame,
    *,
    tol: float = 0.02,
    zone_by_resource: dict[str, str] | None = None,
) -> dict:
    """`precio_bolsa` must already be COP/MWh (loaders.load_precio_bolsa does it)."""
    d = dispo[dispo["dispo"] > 0][["datetime", "resource_name", "gen_type"]].copy()
    d["gen_type"] = d["gen_type"].fillna("SIN_TIPO")  # NaN would break sorting/JSON
    d["day"] = d["datetime"].dt.normalize()
    o = ofertas.assign(day=ofertas["Date"].dt.normalize())
    o = o.drop_duplicates(["day", "resource_name"], keep="last")
    o = o.assign(offer=o["Value"].astype(float) * 1e3)[["day", "resource_name", "offer"]]
    spot = precio_bolsa.rename(columns={"precio_bolsa": "spot"})[["datetime", "spot"]]
    spot = spot.dropna().drop_duplicates("datetime", keep="last")

    # hours that actually have a spot price: the denominator of every share
    hours = spot.assign(hour=spot["datetime"].dt.hour)
    obs = hours.groupby("hour")["datetime"].count()

    m = d.merge(o, on=["day", "resource_name"], how="inner").merge(spot, on="datetime", how="inner")
    m = m[(m["offer"] - m["spot"]).abs() <= tol * m["spot"].abs()]
    m["weight"] = 1.0 / m.groupby("datetime")["resource_name"].transform("count")
    m["hour"] = m["datetime"].dt.hour

    zones = zone_by_resource or {}
    norm = {normalize_name(k): v for k, v in zones.items()}
    m["zone"] = m["resource_name"].map(lambda r: norm.get(normalize_name(r)))

    matched_hours = m["datetime"].nunique()
    ambiguous_hours = int((m.groupby("datetime")["resource_name"].count() > 1).sum())
    total_hours = int(obs.sum())

    cells = []
    if not m.empty:
        grouped = m.groupby(["gen_type", "zone", "hour"], dropna=False)["weight"].sum()
        for (gen_type, zone, hour), weight in grouped.items():
            cells.append(
                {
                    "gen_type": gen_type,
                    "zone": None if pd.isna(zone) else zone,
                    "hour": int(hour),
                    "share": round(float(weight / obs[hour]), 4),
                }
            )
    cells.sort(key=lambda c: (c["hour"], c["gen_type"], c["zone"] or ""))
    mapped = float(m["zone"].notna().mean()) if (zones and not m.empty) else None
    return {
        "tol": tol,
        "n_hours": total_hours,
        "attributed_share": round(matched_hours / total_hours, 4) if total_hours else 0.0,
        "ambiguous_share": round(ambiguous_hours / total_hours, 4) if total_hours else 0.0,
        "zone_mapped_share": None if mapped is None else round(mapped, 4),
        "cells": cells,
    }
