"""Loaders for XM's actual predispatch results (the evaluation targets)."""

from datetime import date

import numpy as np
import pandas as pd

from app.data.heuristic.biddings import parse_mpo
from app.data.paths import resolve_input
from app.storage import get_storage


def load_actual_price(dispatch_date: date, data_dir: str = "data") -> np.ndarray:
    """XM marginal price (MPO) for the date as a 24-length float array, read
    from the per-date iMAR file's "MPO" row (COP/MWh)."""
    path = resolve_input("iMAR", dispatch_date, data_dir)
    with open(path, encoding="latin1") as f:
        raw = f.read()
    return np.array(parse_mpo(raw))


def load_actual_dispatch(dispatch_date: date, data_dir: str = "data") -> pd.DataFrame:
    """XM predispatch generation matrix for the date (raw, latin1-encoded)."""
    storage = get_storage(data_dir)
    with storage.open(f"preideal_dispatch/{dispatch_date}.txt", "rb") as f:
        return pd.read_csv(f, header=None, encoding="latin1")
