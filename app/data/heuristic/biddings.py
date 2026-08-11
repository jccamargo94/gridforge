"""Estima ofertas.csv para fechas donde PrecOferDesp aun no publica.

PrId (generacion despachada por recurso/hora) y iMAR (costo marginal/MPO
nacional por hora) estan frescos hasta hoy, a diferencia de PrecOferDesp
(un mes de rezago). Este modulo cruza ambos para detectar que recurso
esta "a media maquina" (candidato a marginar) cada hora, y le asigna el
MPO de la hora en que se resuelve como su precio de oferta -- ver
docs/superpowers/specs/2026-08-11-ofertas-heuristica-precios-design.md.
"""

import csv
import io
from datetime import date

import pandas as pd
from thefuzz import fuzz, process

from app.data.paths import resolve_input
from app.storage import get_storage

_HOURS = range(24)


def parse_predespacho(raw_text: str) -> dict[str, list[float]]:
    """PrId: una fila por recurso, sin encabezado, `nombre,v0,v1,...,v23`."""
    out: dict[str, list[float]] = {}
    for line in csv.reader(io.StringIO(raw_text)):
        if len(line) < 25:
            continue
        out[line[0].strip()] = [float(v) for v in line[1:25]]
    return out


def parse_mpo(raw_text: str) -> list[float]:
    """iMAR: filas 'Costo Marginal'/'Delta'/'MPO', 24 valores cada una (COP/MWh)."""
    for line in csv.reader(io.StringIO(raw_text)):
        if line and line[0].strip().strip('"') == "MPO":
            values = [float(v) for v in line[1:25]]
            if len(values) != 24:
                raise ValueError(
                    f"la fila 'MPO' del archivo iMAR trae {len(values)} valores, se esperaban 24"
                )
            return values
    raise ValueError("no se encontro la fila 'MPO' en el archivo iMAR")


def detect_marginal_resources(
    predespacho: dict[str, list[float]],
    dispo_declarada: dict[str, list[float]],
) -> dict[str, int]:
    """Devuelve {recurso: hora} para los recursos resueltos por eliminacion.

    Candidato a marginar en la hora h: 0 < despachado[h] < disponible[h]
    ("a media maquina"). Una hora con un unico candidato restante resuelve
    ese recurso -- su precio real es el MPO de esa hora -- y lo elimina
    como candidato de todas las demas horas (solo puede tener un precio,
    porque su oferta es plana durante el dia). Recursos que nunca quedan
    como unico candidato de ninguna hora no se resuelven aqui.

    `despachado`/`disponible` deben venir en la misma unidad (MW) -- ver nota
    de unidades en `ensure_ofertas_estimado`. Si un recurso es candidato unico
    en mas de una hora simultaneamente, se resuelve con la primera en orden de
    hora (0->23); es una eleccion arbitraria pero determinista, no un bug.
    """
    candidates: dict[int, set[str]] = {h: set() for h in _HOURS}
    for resource, despacho in predespacho.items():
        disponible = dispo_declarada.get(resource)
        # ponytail: ambos parsers garantizan 24 valores, pero dispo_declarada
        # viene de un groupby externo (horas incompletas para el recurso ese
        # dia) -- se descarta en vez de reventar con IndexError mas abajo.
        if disponible is None or len(disponible) != 24 or len(despacho) != 24:
            continue
        for h in _HOURS:
            if 0 < despacho[h] < disponible[h]:
                candidates[h].add(resource)

    resolved: dict[str, int] = {}
    changed = True
    while changed:
        changed = False
        for h, resources in candidates.items():
            if len(resources) == 1:
                (resource,) = resources
                if resource not in resolved:
                    resolved[resource] = h
                    changed = True
                for other_resources in candidates.values():
                    other_resources.discard(resource)
    return resolved


def estimate_ofertas(
    dispatch_date: date,
    predespacho: dict[str, list[float]],
    dispo_declarada: dict[str, list[float]],
    mpo_by_hour: list[float],
    ultimo_precio: dict[str, float],
) -> pd.DataFrame:
    """Fila `ofertas` estimada para `dispatch_date`, un renglon por cada recurso
    resuelto como marginal (ver `detect_marginal_resources`) o presente en
    `ultimo_precio` (la union de ambos conjuntos -- un recurso resuelto sin
    precio historico previo igual recibe fila, usando su MPO inferido; uno sin
    resolver usa el ultimo precio publicado sin cambio)."""
    resolved = detect_marginal_resources(predespacho, dispo_declarada)
    rows = []
    for resource in set(ultimo_precio) | set(resolved):
        if resource in resolved:
            value = mpo_by_hour[resolved[resource]] / 1e3
        else:
            value = ultimo_precio[resource]
        rows.append(
            {
                "Date": pd.Timestamp(dispatch_date),
                "resource_name": resource,
                "Value": value,
                "is_estimated": True,
            }
        )
    return pd.DataFrame(rows, columns=["Date", "resource_name", "Value", "is_estimated"])


def _match_resource_name(raw_name: str, resource_names: list[str]) -> str | None:
    match = process.extractOne(
        query=raw_name.lower(),
        choices=resource_names,
        scorer=fuzz.partial_ratio,
        processor=lambda x: x.lower().replace(" ", ""),
        score_cutoff=70,
    )
    return match[0] if match else None


def ensure_ofertas_estimado(
    dispatch_date: date,
    data_dir: str,
    dispo: pd.DataFrame,
    oferta_full: pd.DataFrame,
) -> pd.DataFrame:
    """Estima (y cachea) las filas `ofertas` para `dispatch_date`. `dispo` debe
    venir ya filtrado a esa fecha. Propaga FileNotFoundError/ValueError si
    PrId/iMAR no estan disponibles o no se pueden parsear -- el llamador decide
    que hacer (ver case_builder.py)."""
    storage = get_storage(data_dir)
    year = dispatch_date.year
    cache_path = f"ofertas_estimado/ofertas_estimado_{year}.csv"

    if storage.exists(cache_path):
        with storage.open(cache_path, "rb") as f:
            cached = pd.read_csv(f, parse_dates=["Date"])
        existing = cached[cached["Date"].dt.date == dispatch_date]
        if not existing.empty:
            return existing.reset_index(drop=True)
    else:
        cached = pd.DataFrame(columns=["Date", "resource_name", "Value", "is_estimated"])

    prid_path = resolve_input("PrId", dispatch_date, data_dir)
    with open(prid_path, encoding="latin1") as f:
        predespacho_raw = parse_predespacho(f.read())

    imar_path = resolve_input("iMAR", dispatch_date, data_dir)
    with open(imar_path, encoding="latin1") as f:
        mpo_by_hour = parse_mpo(f.read())

    resource_names = list(dispo["resource_name"].unique())
    predespacho = {}
    for raw_name, values in predespacho_raw.items():
        matched = _match_resource_name(raw_name, resource_names)
        if matched is not None:
            predespacho[matched] = values

    # dispo_declarada.csv esta en kW (case_builder.py hace *1e-3 -> MW bajo
    # "# Valores en MWh"); PrId (predespacho, generacion despachada) esta en MW
    # crudo, sin escalar (mismo convenio documentado en agc.py). Sin este *1e-3
    # aqui, "disponible" queda ~1000x mas grande que "despachado" siempre, la
    # regla "a media maquina" nunca filtra nada, y todo cae al fallback en
    # silencio -- no lo detectes por un test fallando, detectalo por unidades.
    dispo_declarada = {
        resource: (group.sort_values("datetime")["dispo"] * 1e-3).tolist()
        for resource, group in dispo.groupby("resource_name")
    }

    ultimo_precio = (
        oferta_full.sort_values("Date").groupby("resource_name")["Value"].last().to_dict()
    )

    estimated = estimate_ofertas(
        dispatch_date, predespacho, dispo_declarada, mpo_by_hour, ultimo_precio
    )

    cached = pd.concat([cached, estimated], ignore_index=True)
    with storage.open(cache_path, "w") as f:
        cached.to_csv(f, index=False)

    return estimated
