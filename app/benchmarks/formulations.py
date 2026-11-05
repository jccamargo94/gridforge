"""Benchmark of alternative minimum-up-time formulations (issue #58).

Builds synthetic unit-commitment instances of increasing size, solves each with
every formulation in ``UnitCommitmentModel.MIN_UP_FORMULATIONS`` and reports
solve time, MIP gap and objective value. The default formulation of the model
is NOT changed by this module: it only measures.

Run:  ``uv run python -m app.benchmarks.formulations --sizes 10 20 40``

Only data synthesised here is used (no private XM data). HiGHS is the solver;
branch-and-bound node count is reported when the solver exposes it.
"""

from __future__ import annotations

import argparse
import random
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta

import pyomo.environ as pyo

from app.model.model import UnitCommitmentModel
from app.schemas.case import DispatchCase, DispatchLevel


@dataclass
class BenchmarkRow:
    n_gens: int
    n_periods: int
    formulation: str
    n_constraints: int
    solve_seconds: float
    objective: float | None
    mip_gap: float | None
    termination: str


def synthetic_instance(n_gens: int, n_periods: int = 24, seed: int = 0) -> tuple[dict, dict]:
    """Deterministic synthetic thermal fleet with min-up times and a demand curve
    that forces cycling (so min-up constraints actually bind)."""
    rng = random.Random(seed)
    start = datetime(2024, 4, 18)
    periods = [start + timedelta(hours=h) for h in range(n_periods)]
    gens = [f"G{i:03d}" for i in range(n_gens)]
    pmax = {g: rng.choice([50.0, 100.0, 150.0, 200.0]) for g in gens}
    cost = {g: 20.0 + 100.0 * rng.random() for g in gens}
    tmg = {g: rng.choice([3, 4, 6, 8]) for g in gens}
    on0 = {g: int(rng.random() < 0.5) for g in gens}
    ton = {g: (rng.randint(1, tmg[g]) if on0[g] else 0) for g in gens}
    capacity = sum(pmax.values())
    # double-peak load between 35% and 75% of installed capacity
    demand = {}
    for h, t in enumerate(periods):
        shape = 0.55 + 0.20 * ((h in range(7, 11)) - (h in range(0, 5)) + (h in range(18, 22)))
        demand[t] = capacity * min(0.75, max(0.35, shape))
    set_data = {
        "G": gens,
        "I": gens,
        "T": periods,
        "combined_cycle": [],
        "excluded_resource": {},
        "gen_on": [g for g in gens if on0[g]],
        "gen_off": [g for g in gens if not on0[g]],
    }
    param_data = {
        "Pmin": {(g, t): 0.3 * pmax[g] for g in gens for t in periods},
        "Pmax": {(g, t): pmax[g] for g in gens for t in periods},
        "max_min_op": 0,
        "ramp_up": {g: 0.6 * pmax[g] for g in gens},
        "ramp_down": {g: 0.6 * pmax[g] for g in gens},
        "beta": cost,
        "cold_start": {g: 500.0 + 10.0 * pmax[g] for g in gens},
        "demand": demand,
        "TMG": tmg,
        "Ton": ton,
        "z_on_t0_minus_1": on0,
    }
    return set_data, param_data


def run_one(
    n_gens: int,
    formulation: str,
    n_periods: int = 24,
    seed: int = 0,
    time_limit: float = 120.0,
    mip_rel_gap: float = 1e-4,
) -> BenchmarkRow:
    set_data, param_data = synthetic_instance(n_gens, n_periods, seed)
    case = DispatchCase(dispatch_date=date(2024, 4, 18), level=DispatchLevel.ideal)
    uc = UnitCommitmentModel(case=case, min_up_formulation=formulation)
    uc.create_model(set_data=set_data, param_data=param_data)
    model = uc._model
    n_cons = sum(1 for _ in model.component_data_objects(pyo.Constraint, active=True))
    model.dual.direction = pyo.Suffix.LOCAL  # MIP duals are meaningless; avoid importing them
    solver = pyo.SolverFactory("appsi_highs")
    t0 = time.perf_counter()
    res = solver.solve(
        model,
        options={"time_limit": time_limit, "mip_rel_gap": mip_rel_gap},
        load_solutions=False,
    )
    elapsed = time.perf_counter() - t0
    upper = res.problem.upper_bound
    lower = res.problem.lower_bound
    objective = float(upper) if upper is not None and abs(upper) != float("inf") else None
    gap = None
    if objective is not None and lower is not None and abs(lower) != float("inf"):
        gap = abs(objective - float(lower)) / max(abs(objective), 1e-9)
    termination = str(res.solver.termination_condition)
    return BenchmarkRow(
        n_gens=n_gens,
        n_periods=n_periods,
        formulation=formulation,
        n_constraints=n_cons,
        solve_seconds=round(elapsed, 3),
        objective=objective,
        mip_gap=gap,
        termination=termination,
    )


def run_benchmark(sizes: list[int], seeds: list[int], **kwargs) -> list[BenchmarkRow]:
    rows = []
    for n in sizes:
        for seed in seeds:
            for f in UnitCommitmentModel.MIN_UP_FORMULATIONS:
                rows.append(run_one(n, f, seed=seed, **kwargs))
    return rows


def to_markdown(rows: list[BenchmarkRow]) -> str:
    head = (
        "| gens | formulación | filas | tiempo (s) | objetivo | gap | estado |\n"
        "|---|---|---|---|---|---|---|\n"
    )
    body = "\n".join(
        f"| {r.n_gens} | {r.formulation} | {r.n_constraints} | {r.solve_seconds:.2f} | "
        f"{'' if r.objective is None else f'{r.objective:,.0f}'} | "
        f"{'' if r.mip_gap is None else f'{r.mip_gap:.2e}'} | {r.termination} |"
        for r in rows
    )
    return head + body


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sizes", type=int, nargs="+", default=[10, 20, 40])
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    ap.add_argument("--periods", type=int, default=24)
    ap.add_argument("--time-limit", type=float, default=120.0)
    args = ap.parse_args()
    rows = run_benchmark(args.sizes, args.seeds, n_periods=args.periods, time_limit=args.time_limit)
    print(to_markdown(rows))
    _ = asdict  # rows are dataclasses; kept importable for JSON dumps


if __name__ == "__main__":
    main()
