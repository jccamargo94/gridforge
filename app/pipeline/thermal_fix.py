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
    cc_groups: dict[str, list[str]] | None = None,
    min_offer: float = MIN_OFFER,
):
    """Devuelve ``(Pmax, demand, fixed, unmatched)`` nuevos.

    ``gene_mw``: columnas ``datetime, resource_name, gen`` ya en MW.
    ``cc_groups``: ciclos combinados, ``{nombre en Gene: [configuraciones del modelo]}``.
    Las configuraciones de un ciclo son excluyentes (solo una opera a la vez), asi que la
    generacion real de la planta se descuenta **una sola vez** de la demanda (acotada por
    la mayor configuracion disponible) y de cada configuracion.
    ``fixed``: ``{planta: MW totales del dia}`` de las plantas efectivamente fijadas.
    ``unmatched``: candidatas (oferta > ``min_offer``) sin serie en Gene.
    """
    cc_groups = {k.upper().strip(): list(v) for k, v in (cc_groups or {}).items()}
    in_cc = {c for cfgs in cc_groups.values() for c in cfgs}

    gene = {}
    for name, grp in gene_mw.groupby(gene_mw["resource_name"].str.upper().str.strip()):
        gene[name] = grp.groupby("datetime")["gen"].sum()

    # grupo = (nombre Gene, [generadores del modelo])
    groups: list[tuple[str, list[str]]] = []
    unmatched: list[str] = []
    for g in thermal_names:
        if g in in_cc or g not in beta.index or beta[g] <= min_offer:
            continue
        key = g.upper().strip()
        if key in gene:
            groups.append((key, [g]))
        else:
            unmatched.append(g)
    for key, cfgs in cc_groups.items():
        cfgs = [c for c in cfgs if c in beta.index]
        if not cfgs or min(beta[c] for c in cfgs) <= min_offer:
            continue
        if key in gene:
            groups.append((key, cfgs))
        else:
            unmatched.append(key)

    new_pmax = dict(Pmax)
    is_dict = isinstance(demand, dict)
    dem = pd.Series(demand, dtype=float).copy()
    fixed: dict[str, float] = {}
    for ts in dem.index:
        removed = 0.0
        for key, members in groups:
            avail = [new_pmax[(m, ts)] for m in members if (m, ts) in new_pmax]
            if not avail:
                continue
            use = min(float(gene[key].get(ts, 0.0)), max(avail))
            if use <= 0:
                continue
            for m in members:
                if (m, ts) in new_pmax:
                    new_pmax[(m, ts)] = max(new_pmax[(m, ts)] - use, 0.0)
            removed += use
            fixed[key] = fixed.get(key, 0.0) + use
        dem[ts] = max(dem[ts] - removed, 0.0)
    new_demand = dem.to_dict() if is_dict else dem
    return new_pmax, new_demand, fixed, sorted(unmatched)
