"""Load the observed year CSVs a merit-order query needs (possibly spanning
two calendar years) and delegate to app.market.merit."""

from __future__ import annotations

import os
from datetime import date

import pandas as pd

from app.data import loaders
from app.market import merit

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
    return tuple(pd.concat(frames, ignore_index=True) for frames in zip(*parts, strict=True))


def merit_position(day: date, own: list[str]) -> dict:
    dispo, ofertas, demanda = _load(day, day)
    return merit.merit_position(dispo, ofertas, demanda, day, own)


def position_series(start: date, end: date, own: list[str]) -> list[dict]:
    if end < start or (end - start).days + 1 > MAX_RANGE_DAYS:
        raise ValueError(f"range must be 1..{MAX_RANGE_DAYS} days")
    dispo, ofertas, demanda = _load(start, end)
    return merit.position_series(dispo, ofertas, demanda, start, end, own)
