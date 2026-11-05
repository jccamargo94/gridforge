from logging import getLogger
from typing import Iterator

import pyomo.environ as pyo

logger = getLogger("thermal_constraints")


def compute_Lr(model, g: str) -> int:
    """
    Compute the minimum online time for generator g
    """
    LR_1 = int(len(model.T))
    LR_2 = max(0, int((model.TMG[g] - model.Ton[g]) * model.z_on_t0_minus_1[g]))
    return min(LR_1, LR_2)


def minimum_online_time_rule_for_online_gen_rule(model, g: str) -> pyo.Constraint:
    """
    Minimum online time constraint for generator g if it start up generating and dispatched
    """
    final_time = [dt for i, dt in enumerate(model.T) if i <= model.Lr[g]]
    return sum(1 - model.z[g, t] for t in final_time) == 0


def minimum_online_time_rule_for_offline_gen_rule(
    model, g: pyo.Set | Iterator, t: pyo.Set | Iterator
) -> pyo.Expression:
    """
    Minimum online time constraint for generator g if not start generating
    """
    t_num = list(model.T).index(t) + 1
    if model.Lr[g] + 1 <= t_num <= len(model.T) - model.TMG[g]:
        summation_index = [
            dt for indx, dt in enumerate(model.T) if t_num <= indx <= t_num + model.TMG[g] - 1
        ]
        if summation_index:
            return sum(model.z[g, dt] for dt in summation_index) >= model.TMG[g] * model.zup[g, t]
        return pyo.Constraint.Skip
    return pyo.Constraint.Skip


def minimum_online_time_for_offline_gen_rule_last_section(
    model, g: pyo.Set | Iterator, t: pyo.Set | Iterator
) -> pyo.Expression:
    """
    Minimum online time constraint for generator g if not start generating
    """
    t_num = list(model.T).index(t) + 1
    if len(model.T) - model.TMG[g] + 1 <= t_num <= len(model.T):
        # if model.Lr[g] + 1 <= t_num <= len(model.T) - model.TMG[g]:
        summation_index = [dt for indx, dt in enumerate(model.T) if t_num <= len(model.T)]
        if summation_index:
            return sum(model.z[g, dt] - model.zup[g, dt] for dt in summation_index) >= 0
        return pyo.Constraint.Skip
    return pyo.Constraint.Skip


def add_minimum_online_time_disaggregated(model) -> None:
    """Disaggregated (Rajan-Takriti style) alternative to the aggregated window rule.

    Replaces ``sum(z[t..t+TMG-1]) >= TMG * zup[t]`` by one inequality per period of
    the window, ``z[t'] >= zup[t]``. Both are equivalent on integer points, but the
    disaggregated form has a tighter LP relaxation (at the cost of more rows).
    Same index range as ``minimum_online_time_rule_for_offline_gen_rule``.
    """
    periods = list(model.T)
    n = len(periods)
    model.minimum_online_time_disaggregated = pyo.ConstraintList(
        doc="Disaggregated minimum online time: z[g,t'] >= zup[g,t] for t' in window"
    )
    for g in model.G:
        tmg = int(model.TMG[g])
        for t_num in range(int(model.Lr[g]) + 1, n - tmg + 1):
            t = periods[t_num - 1]
            for idx in range(t_num, t_num + tmg):
                model.minimum_online_time_disaggregated.add(
                    model.z[g, periods[idx]] >= model.zup[g, t]
                )
