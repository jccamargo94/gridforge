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
            return [float(v) for v in line[1:25]]
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
        if disponible is None:
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
