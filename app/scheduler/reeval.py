"""Re-evaluate a finished run's metrics against the final reference without
re-solving (spec sections 2 and 3.3): iMAR(D) final for preideal, bolsa
TX1(D) for ideal. Overwrites the same metric_set row (unique per run),
stamping reference + evaluated_at so a provisional-vs-iMAR score is never
mistaken for a settled-vs-TX1 one. Dispatch columns are kept: they need the
solved model, which post-hoc re-evaluation does not have.
"""

from __future__ import annotations

import pandas as pd

from app.data import download
from app.data.actuals import load_actual_bolsa, load_actual_price
from app.db import queries
from app.storage import get_storage
from app.utils.metrics import price_metrics

REEVAL_SOURCE_KIND = {
    "reeval_preideal": "preideal_daily",
    "reeval_ideal": "ideal_daily",
}

REEVAL_REFERENCE = {
    "reeval_preideal": "iMAR",
    "reeval_ideal": "bolsa_tx1",
}

_ACTUAL_BY_REFERENCE = {
    "iMAR": load_actual_price,
    "bolsa_tx1": load_actual_bolsa,
}


def _model_mpo(run) -> list[float]:
    if run.price_path is None:
        raise ValueError("run tiene price_path nulo; no hay precio modelo que reevaluar")
    with get_storage(".").open(run.price_path) as f:
        price_df = pd.read_csv(f, parse_dates=["datetime"]).sort_values("datetime")
    return price_df["ideal_marginal_price"].astype(float).tolist()


def reevaluate_metrics(session, run, *, reference: str, data_dir: str = "data") -> dict[str, float]:
    actual_fn = _ACTUAL_BY_REFERENCE.get(reference)
    if actual_fn is None:
        raise ValueError(f"referencia desconocida: {reference!r}")
    model_mpo = _model_mpo(run)
    case = queries.get_case(session, run.case_id)
    if case is None:
        raise ValueError(f"run {run.id} sin case")
    if reference == "iMAR":
        # The reeval must always read the FINAL iMAR(D): XM modifies the blob
        # up to ~165 min after its ~09:58 creation, and ensure_data_for_date
        # never refreshes an existing file — force-refresh it first (bolsa_tx1
        # needs no refresh: the year CSV is kept fresh by the refresh tick).
        download.force_refresh_blob("iMAR", case.dispatch_date, data_dir)
    xm = actual_fn(case.dispatch_date, data_dir=data_dir)
    n = min(len(xm), len(model_mpo))
    metrics = price_metrics(xm[:n], model_mpo[:n])
    queries.update_metric_set(session, run.id, metrics=metrics, reference=reference)
    return metrics
