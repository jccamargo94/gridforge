"""Loaders for XM's actual predispatch results (the evaluation targets)."""

from datetime import date

import numpy as np

from app.data.heuristic.biddings import parse_mpo, parse_predespacho
from app.data.loaders import load_precio_bolsa
from app.data.paths import resolve_input


def load_actual_price(dispatch_date: date, data_dir: str = "data") -> np.ndarray:
    """XM marginal price (MPO) for the date as a 24-length float array, read
    from the per-date iMAR file's "MPO" row (COP/MWh)."""
    path = resolve_input("iMAR", dispatch_date, data_dir)
    with open(path, encoding="latin1") as f:
        raw = f.read()
    return np.array(parse_mpo(raw))


def load_actual_bolsa(dispatch_date: date, data_dir: str = "data") -> np.ndarray:
    """XM real national bolsa price (PrecBolsNaci) for the date as a 24-length
    float array (COP/MWh), read from the year-level precio_bolsa CSV."""
    df = load_precio_bolsa(data_dir, dispatch_date.year)
    sub = df[df["datetime"].dt.date == dispatch_date].sort_values("datetime")
    if sub.empty:
        raise ValueError(f"precio de bolsa real (PrecBolsNaci) no publicada para {dispatch_date}")
    return sub["precio_bolsa"].astype(float).to_numpy()


def load_reference_price(dispatch_date: date, level: str, data_dir: str = "data") -> np.ndarray:
    """Pick the evaluation reference for a run.

    ideal/lmp -> real bolsa price (PrecBolsNaci): the value the ideal dispatch
    determines, and the target the LMP weighted-average price is compared
    against; falls back to iMAR MPO when not yet published. preideal -> iMAR MPO.
    """
    if level in ("ideal", "lmp"):
        try:
            return load_actual_bolsa(dispatch_date, data_dir=data_dir)
        except (FileNotFoundError, ValueError):
            return load_actual_price(dispatch_date, data_dir=data_dir)
    return load_actual_price(dispatch_date, data_dir=data_dir)


def load_actual_dispatch(dispatch_date: date, data_dir: str = "data") -> dict[str, list[float]]:
    """XM predespacho ideal generation per resource for the date as
    {resource: [24 hourly MW]}, read from the per-date PrId file."""
    path = resolve_input("PrId", dispatch_date, data_dir)
    with open(path, encoding="latin1") as f:
        return parse_predespacho(f.read())
