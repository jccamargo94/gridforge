"""Cross declared availability against PARATEC net effective capacity (issue #84).

Compares two observed sources that live in different XM systems:
  - dispo_declarada year CSV (pydataxm DispoDeclarada), hourly, kW -> MW (x1e-3)
  - PARATEC `NetEffectiveCapacities/getNetEffectiveCapacity` cached by the
    topology scrape (data/topology/raw/capacity.json), MW (the same field the
    nodal builder uses as Generator.p_max).

What is NOT done, on purpose: the issue also mentions `technicalMinimum` from
ThermalPlant/getThermalPlantDetail. No payload in this repo (code, fixtures or
tests) shows that field, so a rule on it would be built on an unverified
schema. Only net effective capacity is crossed.

Crosswalk. XM resource names (ListadoRecursos) and PARATEC `elementName` are
matched by exact normalized name (lowercase, no accents/punctuation) -- no fuzzy
matching, a wrong plant is worse than an unmatched one. Coverage is reported;
names that normalize to more than one PARATEC element are skipped as ambiguous.

Rules (all parameters are explicit and returned with the result):
  - exceeds_capacity: daily peak declared MW > capacity * (1 + over_tol).
  - persistent_low: >= min_days consecutive days whose daily peak declared MW is
    below low_pct * capacity (and not zero: fully unavailable days are a
    maintenance/outage signal reported separately as `outage_days`).
  - hour_pattern: hours of the day with zero declared availability on >= 80% of
    the days that otherwise had availability.
"""

from __future__ import annotations

import pandas as pd

from app.market.marginal import normalize_name

HOUR_PATTERN_SHARE = 0.8


def capacity_by_name(generators: list[dict]) -> tuple[dict[str, float], list[str]]:
    """normalized name -> MW, plus the normalized names that collide."""
    caps: dict[str, float] = {}
    collisions: set[str] = set()
    for g in generators:
        key = normalize_name(g["name"])
        if key in caps:
            collisions.add(key)
        caps[key] = float(g["capacity"])
    for key in collisions:
        caps.pop(key, None)
    return caps, sorted(collisions)


def _longest_run(flags: list[bool]) -> int:
    best = cur = 0
    for f in flags:
        cur = cur + 1 if f else 0
        best = max(best, cur)
    return best


def check_availability(
    dispo: pd.DataFrame,
    capacity: dict[str, float],
    *,
    low_pct: float = 0.5,
    min_days: int = 3,
    over_tol: float = 0.02,
) -> dict:
    d = dispo.dropna(subset=["resource_name"]).copy()
    d["day"] = d["datetime"].dt.normalize()
    d["hour"] = d["datetime"].dt.hour
    d["mw"] = d["dispo"].astype(float) * 1e-3

    findings = []
    matched = 0
    unmatched: list[str] = []
    for resource, g in d.groupby("resource_name"):
        cap = capacity.get(normalize_name(resource))
        if cap is None or cap <= 0:
            unmatched.append(resource)
            continue
        matched += 1
        daily = g.groupby("day")["mw"].max().sort_index()
        over = daily[daily > cap * (1 + over_tol)]
        outage = daily[daily <= 0]
        low_flags = [(0 < v < low_pct * cap) for v in daily.to_numpy()]
        low_run = _longest_run(low_flags)

        active_days = daily[daily > 0].index
        zero_hours: list[int] = []
        if len(active_days) >= 5:
            act = g[g["day"].isin(active_days)]
            zero_share = act.groupby("hour")["mw"].apply(lambda s: float((s <= 0).mean()))
            zero_hours = sorted(
                int(h)
                for h, share in zero_share.items()
                if share >= HOUR_PATTERN_SHARE and len(zero_share) > 0
            )
            if len(zero_hours) == 24:
                zero_hours = []

        issues = []
        if len(over):
            issues.append("exceeds_capacity")
        if low_run >= min_days:
            issues.append("persistent_low")
        if zero_hours:
            issues.append("hour_pattern")
        if issues or len(outage):
            findings.append(
                {
                    "resource": resource,
                    "capacity_mw": round(cap, 3),
                    "issues": issues,
                    "days_observed": int(len(daily)),
                    "days_over_capacity": int(len(over)),
                    "max_ratio_to_capacity": round(float(daily.max() / cap), 3),
                    "longest_low_run_days": int(low_run),
                    "outage_days": int(len(outage)),
                    "zero_hours": zero_hours,
                }
            )
    findings.sort(key=lambda f: (-len(f["issues"]), f["resource"]))
    total = matched + len(unmatched)
    return {
        "params": {"low_pct": low_pct, "min_days": min_days, "over_tol": over_tol},
        "resources_in_dispo": total,
        "matched": matched,
        "match_rate": round(matched / total, 4) if total else 0.0,
        "unmatched_resources": sorted(unmatched),
        "findings": findings,
    }
