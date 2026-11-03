"""Termicas fijas a su generacion real (inflexibilidades) en el despacho ideal.

El precio ideal (CREG 051/2009, 011/2010) excluye las inflexibilidades: la
energia de plantas que generaron fuera de merito no fija precio. Aproximacion
*residual*: la generacion real de cada termica se descuenta de la demanda y de su
``Pmax`` horario; la oferta de la planta queda intacta para su disponibilidad
restante, de modo que sigue pudiendo fijar el precio cuando es marginal.

Validado en 29 fechas reales de 2026 (issue #63): WAPE medio sin dI 11,21 -> 7,09;
20 fechas mejoran, 8 empeoran (dias caros de punta, donde la generacion termica
real incluye energia economica y no solo inflexible).
"""

import pandas as pd

# Solo termicas con oferta por encima de este valor (COP/MWh): las baratas no son
# candidatas a inflexibilidad. Valor usado en la validacion; no se ha calibrado.
MIN_OFFER = 125_000.0


def apply_thermal_real_generation(
    Pmax: dict,
    demand,
    beta: pd.Series,
    thermal_names,
    gene_mw: pd.DataFrame,
    *,
    min_offer: float = MIN_OFFER,
):
    """Devuelve ``(Pmax, demand, fixed)`` nuevos.

    ``gene_mw``: columnas ``datetime, resource_name, gen`` ya en MW.
    ``fixed``: ``{planta: MW totales del dia}`` de las plantas efectivamente fijadas.
    """
    gene = {}
    for name, grp in gene_mw.groupby(gene_mw["resource_name"].str.upper().str.strip()):
        gene[name] = grp.groupby("datetime")["gen"].sum()

    selected = [
        g
        for g in thermal_names
        if g in beta.index and beta[g] > min_offer and g.upper().strip() in gene
    ]
    new_pmax = dict(Pmax)
    is_dict = isinstance(demand, dict)
    dem = pd.Series(demand, dtype=float).copy()
    fixed: dict[str, float] = {}
    for ts in dem.index:
        removed = 0.0
        for g in selected:
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
