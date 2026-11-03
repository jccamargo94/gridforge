"""Load the observed year CSVs a merit-order query needs (possibly spanning
two calendar years) and delegate to app.market.merit."""

from __future__ import annotations

import json
import os
from datetime import date, timedelta

import pandas as pd

from app.data import loaders
from app.market import marginal, merit, offer_audit
from app.storage import get_storage

MAX_RANGE_DAYS = 92


def data_dir() -> str:
    return os.environ.get("DATA_DIR", "data")


def _years(start: date, end: date) -> range:
    return range(start.year, end.year + 1)


def _load(start: date, end: date) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Raises FileNotFoundError when a needed year CSV is not present."""
    dd = data_dir()
    parts = [
        (loaders.load_dispo(dd, y), loaders.load_ofertas(dd, y), loaders.load_demanda(dd, y))
        for y in _years(start, end)
    ]
    dispo, ofertas, demanda = (
        pd.concat(frames, ignore_index=True) for frames in zip(*parts, strict=True)
    )
    # Pre-filter to the requested window so per-day work does not rescan whole
    # year frames, and drop duplicate (resource, hour) rows the way case_builder does.
    lo, hi = pd.Timestamp(start), pd.Timestamp(end) + pd.Timedelta(days=1)
    dispo = dispo[(dispo["datetime"] >= lo) & (dispo["datetime"] < hi)]
    dispo = dispo.dropna(subset=["resource_name"]).drop_duplicates(
        ["resource_name", "datetime"], keep="last"
    )
    ofertas = ofertas[(ofertas["Date"] >= lo) & (ofertas["Date"] < hi)]
    demanda = demanda[(demanda["datetime"] >= lo) & (demanda["datetime"] < hi)]
    return dispo, ofertas, demanda


def load_offer_history(start: date, end: date) -> pd.DataFrame:
    """Observed daily offers (ofertas.csv) in [start, end]; FileNotFoundError if a
    year CSV is missing."""
    dd = data_dir()
    frames = [loaders.load_ofertas(dd, y) for y in _years(start, end)]
    ofertas = pd.concat(frames, ignore_index=True)
    lo, hi = pd.Timestamp(start), pd.Timestamp(end) + pd.Timedelta(days=1)
    return ofertas[(ofertas["Date"] >= lo) & (ofertas["Date"] < hi)]


def merit_position(day: date, own: list[str]) -> dict:
    dispo, ofertas, demanda = _load(day, day)
    return merit.merit_position(dispo, ofertas, demanda, day, own)


def position_series(start: date, end: date, own: list[str]) -> list[dict]:
    if end < start or (end - start).days + 1 > MAX_RANGE_DAYS:
        raise ValueError(f"range must be 1..{MAX_RANGE_DAYS} days")
    dispo, ofertas, demanda = _load(start, end)
    return merit.position_series(dispo, ofertas, demanda, start, end, own)


def audit_offers(day: date, offers: list[tuple[str, float | None]], window_days: int) -> list[dict]:
    if not 7 <= window_days <= 365:
        raise ValueError("window_days must be 7..365")
    history = load_offer_history(day - timedelta(days=window_days), day)
    return [offer_audit.audit_offer(history, r, day, p, window_days) for r, p in offers]


MAX_MARGINAL_DAYS = 366
# Same cache file POST /topology/scrape writes (services/api/main.py).
TOPOLOGY_NETWORK_PATH = "topology/network.json"


def _zone_by_resource() -> dict[str, str]:
    """resource -> zone from the cached PARATEC network; {} when not scraped yet."""
    storage = get_storage(data_dir())
    if not storage.exists(TOPOLOGY_NETWORK_PATH):
        return {}
    with storage.open(TOPOLOGY_NETWORK_PATH) as fh:
        network = json.load(fh)
    return {g["name"]: g["zone"] for g in network.get("generators", []) if g.get("zone")}


def marginal_map(start: date, end: date, tol: float) -> dict:
    if end < start or (end - start).days + 1 > MAX_MARGINAL_DAYS:
        raise ValueError(f"range must be 1..{MAX_MARGINAL_DAYS} days")
    if not 0.0 <= tol <= 0.2:
        raise ValueError("tol must be between 0 and 0.2")
    dispo, ofertas, _ = _load(start, end)
    dd = data_dir()
    spot = pd.concat(
        [loaders.load_precio_bolsa(dd, y) for y in _years(start, end)], ignore_index=True
    )
    lo, hi = pd.Timestamp(start), pd.Timestamp(end) + pd.Timedelta(days=1)
    spot = spot[(spot["datetime"] >= lo) & (spot["datetime"] < hi)]
    return marginal.marginal_map(
        dispo, ofertas, spot, tol=tol, zone_by_resource=_zone_by_resource()
    )
