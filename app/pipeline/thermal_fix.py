"""Fix inflexible thermal units to their real generation in the ideal dispatch.

The ideal price (CREG 051/2009, 011/2010) excludes inflexibilities: energy from
plants that generated out of merit must not set the price. The residual
approximation subtracts each thermal unit's real generation from hourly ``Pmax``
and from demand. The unit's offer is left untouched for its remaining
availability, so it can still set the marginal price when it is economic.

Selection is per (generator, hour) and uses the real bolsa spot price: a unit is
fixed only in hours where its offer exceeds spot (it would not be economic
there). Units in merit keep their availability. When spot data is unavailable or
empty, no generation is fixed.
"""

import pandas as pd


def apply_thermal_real_generation(
    Pmax: dict,
    demand,
    beta: pd.Series,
    thermal_names,
    gene_mw: pd.DataFrame,
    *,
    spot: pd.Series,
):
    """Return new ``(Pmax, demand, fixed)``.

    ``gene_mw``: columns ``datetime, resource_name, gen``, already in MW.
    ``spot``: hourly real bolsa spot price (COP/MWh) indexed by timestamp.
    ``fixed``: ``{plant: total MW fixed over the day}`` for units actually fixed.
    """
    gene = {}
    for name, grp in gene_mw.groupby(gene_mw["resource_name"].str.upper().str.strip()):
        gene[name] = grp.groupby("datetime")["gen"].sum()

    candidates = [g for g in thermal_names if g in beta.index and g.upper().strip() in gene]
    new_pmax = dict(Pmax)
    is_dict = isinstance(demand, dict)
    dem = pd.Series(demand, dtype=float).copy()
    fixed: dict[str, float] = {}
    for ts in dem.index:
        spot_t = spot.get(ts)
        if spot_t is None or pd.isna(spot_t):
            continue
        removed = 0.0
        for g in candidates:
            if beta[g] <= spot_t:
                continue
            key = (g, ts)
            if key not in new_pmax:
                continue
            use = min(float(gene[g.upper().strip()].get(ts, 0.0)), new_pmax[key])
            if use <= 0:
                continue
            new_pmax[key] = max(new_pmax[key] - use, 0.0)
            removed += use
            fixed[g] = fixed.get(g, 0.0) + use
        dem[ts] = max(dem[ts] - removed, 0.0)
    new_demand = dem.to_dict() if is_dict else dem
    return new_pmax, new_demand, fixed
