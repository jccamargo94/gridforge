"""Generacion despachada en PrId por plantas que el modelo no tiene.

PrId lista todas las plantas que XM despacha, pero el modelo solo conoce las
que aparecen en la disponibilidad (declarada/DispoCome). Plantas nuevas (p.ej.
solares o eolicas recien entradas) pueden estar en PrId sin registro de
disponibilidad: su energia no tiene oferente en el modelo y el balance queda
corto por esos MW. Como el escalon entre la oferta barata y la termica es de
~100k COP/MWh, un faltante de decenas de MW dispara el precio (ver issue #63,
2026-04-29). Se tratan como generacion fija: se descuentan de la demanda.
"""

import csv
import re

from thefuzz import fuzz, process

MATCH_CUTOFF = 85
_AGGREGATE_ROWS = {"total"}  # filas agregadas (p.ej. fixture sintetico), no plantas
_scorer = fuzz.token_sort_ratio


def _norm(name: str) -> str:
    return name.strip().lower().replace(" ", "")


def _ident(name: str) -> tuple[str, frozenset[str]]:
    """Identificador de una planta: ultimo token y tokens con digitos.

    Evita que hermanas numeradas ("... 4" vs "... 5", "ESCOBAL I" vs "II",
    "BSLI" vs "BSLII"), que el fuzzy puntua >= 90, se confundan entre si.
    """
    toks = [t for t in re.split(r"[\s\-]+", name.strip().lower()) if t]
    return (toks[-1] if toks else "", frozenset(t for t in toks if any(c.isdigit() for c in t)))


def prid_unmodeled_mw(prid_path: str, known_names, *, encoding: str = "latin1"):
    """(MW por hora [24], {planta: MW totales del dia}) de plantas de PrId sin recurso conocido.

    Una planta cuenta como conocida si coincide exacta (sin espacios/mayusculas) o
    con `token_sort_ratio >= MATCH_CUTOFF` con algun nombre de `known_names` Y el mismo
    identificador (ultimo token y numeros), para no absorber plantas hermanas.
    """
    raw = {_norm(n): n for n in known_names if isinstance(n, str)}
    known = set(raw)
    known_list = sorted(known)
    hours = [0.0] * 24
    detail: dict[str, float] = {}
    with open(prid_path, encoding=encoding) as fh:
        for row in csv.reader(fh):
            if len(row) < 25:
                continue
            name = row[0].strip()
            vals = [float(v) for v in row[1:25]]
            if sum(vals) <= 0:
                continue
            key = _norm(name)
            if key in _AGGREGATE_ROWS or key in known:
                continue
            if known_list and any(
                _ident(raw[cand]) == _ident(name)
                for cand, score in process.extract(key, known_list, scorer=_scorer, limit=5)
                if score >= MATCH_CUTOFF
            ):
                continue
            detail[name] = sum(vals)
            hours = [a + b for a, b in zip(hours, vals, strict=True)]
    return hours, detail
