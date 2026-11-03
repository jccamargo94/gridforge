"""Merit order / competitive position from observed XM data (issue #82).

Pure pandas, no Pyomo and no case_builder: the merit order is "sort the
declared-available resources by their offer price and stack their capacity".

Inputs are the year CSVs read by app/data/loaders.py, *unscaled*; the unit
conversions live here, with the same factors case_builder.py applies
(verified there, not from memory):
  - dispo_declarada.dispo: kW  -> MW      (x1e-3)
  - ofertas.Value: COP/kWh -> COP/MWh     (x1e3), ONE price per resource per day
  - demaCome.dema: kWh/h -> MW            (x1e-3)

Privacy policy (product rule, see the issue's "Limites"): per-rival offers are
never returned. Rivals appear only aggregated by technology, and a technology
group with fewer than `MIN_GROUP_SIZE` rival resources is folded into "OTROS"
so an aggregate cannot be inverted into one competitor's price.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

MIN_GROUP_SIZE = 3
OTHERS = "OTROS"
HOURS = range(24)


def _day_frame(
    dispo: pd.DataFrame, ofertas: pd.DataFrame, demanda: pd.DataFrame, day: date
) -> tuple[pd.DataFrame, dict[int, float], float]:
    """Long frame (hour, resource_name, gen_type, cap_mw, price) for one day,
    demand MW per hour, and the declared MW that has no offer that day."""
    d = dispo[dispo["datetime"].dt.date == day].copy()
    d["hour"] = d["datetime"].dt.hour
    d["cap_mw"] = d["dispo"].astype(float) * 1e-3
    d = d[d["cap_mw"] > 0]

    o = ofertas[ofertas["Date"].dt.date == day]
    prices = (
        o.drop_duplicates("resource_name", keep="last")
        .set_index("resource_name")["Value"]
        .astype(float)
        * 1e3
    )
    d["price"] = d["resource_name"].map(prices)
    unpriced_mw = float(d.loc[d["price"].isna(), "cap_mw"].sum()) / max(d["hour"].nunique(), 1)
    d = d.dropna(subset=["price"])

    dem = demanda[demanda["datetime"].dt.date == day]
    demand_mw = {
        int(h): float(v) * 1e-3
        for h, v in zip(dem["datetime"].dt.hour, dem["dema"].astype(float), strict=True)
    }
    return d[["hour", "resource_name", "gen_type", "cap_mw", "price"]], demand_mw, unpriced_mw


def _rank_hour(h: pd.DataFrame, demand_mw: float | None) -> pd.DataFrame:
    """Add rank / cum_ahead_mw / in_merit for one hour. Ties share a rank:
    only strictly cheaper offers count as "ahead", so the result does not
    depend on an arbitrary tie-break."""
    price = h["price"].to_numpy()
    cap = h["cap_mw"].to_numpy()
    cheaper = price[None, :] < price[:, None]
    out = h.copy()
    out["rank"] = cheaper.sum(axis=1) + 1
    out["cum_ahead_mw"] = (cheaper * cap[None, :]).sum(axis=1)
    out["in_merit"] = (
        out["cum_ahead_mw"] < demand_mw
        if demand_mw is not None
        else pd.Series(False, index=h.index)
    )
    return out


def _clearing_price(h: pd.DataFrame, demand_mw: float | None) -> float | None:
    """Offer price of the offer that covers demand (None if demand is unknown
    or exceeds the priced supply). It is a system-level number, not a name."""
    if demand_mw is None or h.empty:
        return None
    s = h.sort_values("price")
    covered = s[s["cap_mw"].cumsum() >= demand_mw]
    return float(covered.iloc[0]["price"]) if not covered.empty else None


def _aggregate_rivals(rivals: pd.DataFrame) -> list[dict]:
    if rivals.empty:
        return []
    r = rivals.copy()
    sizes = r.groupby("gen_type")["resource_name"].transform("nunique")
    r.loc[sizes < MIN_GROUP_SIZE, "gen_type"] = OTHERS
    # a leftover OTROS bucket that is still too small must not be published
    if (r["gen_type"] == OTHERS).any() and r.loc[
        r["gen_type"] == OTHERS, "resource_name"
    ].nunique() < MIN_GROUP_SIZE:
        r = r[r["gen_type"] != OTHERS]
    rows = []
    for tech, g in r.groupby("gen_type"):
        cap = float(g["cap_mw"].sum())
        rows.append(
            {
                "gen_type": tech,
                "n_resources": int(g["resource_name"].nunique()),
                "capacity_mw": round(cap, 3),
                "avg_price_cop_mwh": round(float(np.average(g["price"], weights=g["cap_mw"])), 3),
                "in_merit_mw": round(float(g.loc[g["in_merit"], "cap_mw"].sum()), 3),
            }
        )
    return sorted(rows, key=lambda x: x["gen_type"])


def merit_position(
    dispo: pd.DataFrame,
    ofertas: pd.DataFrame,
    demanda: pd.DataFrame,
    day: date,
    own: list[str],
) -> dict:
    """Hour-by-hour position of the `own` resources in the day's merit order."""
    frame, demand_by_hour, unpriced_mw = _day_frame(dispo, ofertas, demanda, day)
    own_set = set(own)
    hours = []
    for hour in HOURS:
        h = frame[frame["hour"] == hour]
        demand = demand_by_hour.get(hour)
        ranked = (
            _rank_hour(h, demand)
            if not h.empty
            else h.assign(rank=[], cum_ahead_mw=[], in_merit=[])
        )
        mine = ranked[ranked["resource_name"].isin(own_set)]
        rivals = ranked[~ranked["resource_name"].isin(own_set)]
        hours.append(
            {
                "hour": hour,
                "demand_mw": None if demand is None else round(demand, 3),
                "n_priced": int(len(ranked)),
                "clearing_price_cop_mwh": _clearing_price(h, demand),
                "own": [
                    {
                        "resource": r.resource_name,
                        "gen_type": r.gen_type,
                        "price_cop_mwh": round(float(r.price), 3),
                        "capacity_mw": round(float(r.cap_mw), 3),
                        "rank": int(r.rank),
                        "cum_ahead_mw": round(float(r.cum_ahead_mw), 3),
                        "in_merit": bool(r.in_merit),
                    }
                    for r in mine.sort_values("rank").itertuples()
                ],
                "market_by_tech": _aggregate_rivals(rivals),
            }
        )
    return {
        "date": day.isoformat(),
        "unpriced_mw_avg": round(unpriced_mw, 3),
        "hours": hours,
    }


def position_series(
    dispo: pd.DataFrame,
    ofertas: pd.DataFrame,
    demanda: pd.DataFrame,
    start: date,
    end: date,
    own: list[str],
) -> list[dict]:
    """One row per (day, own resource): how its position evolves over time."""
    rows = []
    for day in pd.date_range(start, end).date:
        pos = merit_position(dispo, ofertas, demanda, day, own)
        per_resource: dict[str, list[dict]] = {}
        for hour in pos["hours"]:
            for item in hour["own"]:
                per_resource.setdefault(item["resource"], []).append(
                    {**item, "n_priced": hour["n_priced"]}
                )
        for resource, items in sorted(per_resource.items()):
            rows.append(
                {
                    "date": day.isoformat(),
                    "resource": resource,
                    "hours_available": len(items),
                    "hours_in_merit": sum(i["in_merit"] for i in items),
                    "avg_rank": round(float(np.mean([i["rank"] for i in items])), 3),
                    "avg_rank_pct": round(
                        float(np.mean([i["rank"] / i["n_priced"] for i in items])), 4
                    ),
                    "price_cop_mwh": items[0]["price_cop_mwh"],
                    "avg_cum_ahead_mw": round(
                        float(np.mean([i["cum_ahead_mw"] for i in items])), 3
                    ),
                }
            )
    return rows
