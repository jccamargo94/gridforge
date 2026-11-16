"""Reproducible price-error decomposition on saved real-date ideal runs.

For every saved ideal run, split the model-vs-bolsa WAPE into the share closed
by the inferred daily additive term (dI) and the residual MPO error. Reads only
already-saved artifacts; never re-solves the model or rewrites the price CSVs.

Usage:
    uv run python measure_price_error.py [--data-dir data] [--results-dir data/results]
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from app.data.actuals import load_actual_bolsa
from app.pipeline.delta_i import delta_i_metrics

PREFIX = "marginal_price-"
SUFFIX = "-ideal.csv"


def discover_ideal_runs(results_dir: Path) -> list[tuple[str, Path]]:
    """Return (date string, csv path) for each saved ideal price CSV.

    Saved runs live one level deep, inside run-hash directories, so nested
    directories are scanned. A date may appear in several runs; one run per
    date is chosen -- the most recently modified file, with ties broken by
    path name for determinism.
    """
    best: dict[str, Path] = {}
    for path in results_dir.rglob(f"{PREFIX}*{SUFFIX}"):
        date_str = path.name[len(PREFIX) : -len(SUFFIX)]
        current = best.get(date_str)
        if current is None or (path.stat().st_mtime_ns, path.name) > (
            current.stat().st_mtime_ns,
            current.name,
        ):
            best[date_str] = path
    return sorted(best.items())


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data", help="root with XM inputs")
    parser.add_argument("--results-dir", default="data/results", help="saved run results")
    args = parser.parse_args(argv)

    results_dir = Path(args.results_dir)
    if not results_dir.is_dir():
        print(f"No results directory at {results_dir}; nothing to measure.")
        return
    runs = discover_ideal_runs(results_dir)
    if not runs:
        print(f"No '{PREFIX}*{SUFFIX}' files under {results_dir}; nothing to measure.")
        return

    rows: list[dict] = []
    skipped = 0
    for date_str, path in runs:
        try:
            dispatch_date = date.fromisoformat(date_str)
            spot = load_actual_bolsa(dispatch_date, data_dir=args.data_dir)
        except (ValueError, FileNotFoundError):
            skipped += 1
            continue
        price_df = pd.read_csv(path, parse_dates=["datetime"]).sort_values("datetime")
        model_mpo = price_df["ideal_marginal_price"].to_numpy(dtype=float)
        metrics = delta_i_metrics(dispatch_date, spot, model_mpo, data_dir=args.data_dir)
        if not metrics:
            skipped += 1
            continue
        rows.append(
            {
                "date": date_str,
                "delta_i": metrics["delta_i"],
                "wape_base": metrics["wape_base"],
                "wape_bolsa_equivalent": metrics["wape_bolsa_equivalent"],
                "wape_closed_by_delta": metrics["wape_closed_by_delta"],
            }
        )

    if not rows:
        print(
            "No eligible ideal runs (missing actuals/offers/dispo or <18 "
            f"matched hours); skipped {skipped}."
        )
        return

    header = (
        f"{'date':<12} {'delta_i':>12} {'wape_base':>11} {'wape_bolsa_eq':>14} {'wape_closed':>12}"
    )
    print(header)
    print("-" * 65)
    for row in rows:
        print(
            f"{row['date']:<12} {row['delta_i']:>12.0f} {row['wape_base']:>11.4f} "
            f"{row['wape_bolsa_equivalent']:>14.4f} {row['wape_closed_by_delta']:>12.4f}"
        )

    base = np.array([r["wape_base"] for r in rows])
    equiv = np.array([r["wape_bolsa_equivalent"] for r in rows])
    closed = np.array([r["wape_closed_by_delta"] for r in rows])
    improved = int(np.sum(equiv < base))
    print("-" * 65)
    print(f"eligible dates: {len(rows)}   skipped: {skipped}")
    print(f"bolsa-equivalent WAPE < base WAPE: {improved}/{len(rows)}")
    aggregates = (
        ("wape_base", base),
        ("wape_bolsa_equivalent", equiv),
        ("wape_closed_by_delta", closed),
    )
    for label, values in aggregates:
        print(f"{label:<22} mean={np.mean(values):.4f}  median={np.median(values):.4f}")


if __name__ == "__main__":
    main()
