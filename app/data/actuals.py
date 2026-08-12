"""Loaders for XM's actual predispatch results (the evaluation targets)."""

from datetime import date

import numpy as np

from app.data.heuristic.biddings import parse_mpo, parse_predespacho
from app.data.paths import resolve_input


def load_actual_price(dispatch_date: date, data_dir: str = "data") -> np.ndarray:
    """XM marginal price (MPO) for the date as a 24-length float array, read
    from the per-date iMAR file's "MPO" row (COP/MWh)."""
    path = resolve_input("iMAR", dispatch_date, data_dir)
    with open(path, encoding="latin1") as f:
        raw = f.read()
    return np.array(parse_mpo(raw))


def load_actual_dispatch(dispatch_date: date, data_dir: str = "data") -> dict[str, list[float]]:
    """XM predespacho ideal generation per resource for the date as
    {resource: [24 hourly MW]}, read from the per-date PrId file."""
    path = resolve_input("PrId", dispatch_date, data_dir)
    with open(path, encoding="latin1") as f:
        return parse_predespacho(f.read())
