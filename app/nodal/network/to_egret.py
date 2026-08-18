from __future__ import annotations

from egret.data.model_data import ModelData

from app.nodal.network.schemas import NodalNetwork


def nodal_to_model_data(net: NodalNetwork, time_keys: list[str]) -> ModelData:
    buses: dict[str, dict] = {
        z.name: {"bus_name": z.name, "vm": 1.0, "va": 0.0, "base_kv": z.base_kv, "zone": z.name}
        for z in net.zones
    }
    generators: dict[str, dict] = {}
    for g in net.generators:
        ramp = g.ramp_rate if g.ramp_rate is not None else g.p_max
        generators[g.name] = {
            "bus": g.zone,
            "generator_type": "thermal",
            "in_service": True,
            "fuel": g.fuel,
            "pg": 0.0,
            "p_min": g.p_min,
            "p_max": g.p_max,
            "p_cost": {
                "data_type": "cost_curve",
                "cost_curve_type": "polynomial",
                "values": {0: g.no_load_cost, 1: g.marginal_cost},
            },
            "ramp_up_60min": ramp,
            "ramp_down_60min": ramp,
            "min_up_time": g.min_up_time,
            "min_down_time": g.min_down_time,
            "initial_status": g.initial_status
            if g.initial_status != 0
            else (-1 if g.initial_status < 0 else 1),
            "initial_p_output": 0.0,
            "startup_cost": [[g.min_down_time, 0.0]],
            "shutdown_cost": 0.0,
        }
    branches: dict[str, dict] = {}
    for b in net.branches:
        branches[b.name] = {
            "from_bus": b.from_zone,
            "to_bus": b.to_zone,
            "reactance": b.reactance,
            "resistance": 0.0,
            "charging_susceptance": 0.0,
            "branch_type": "line",
            "rating_long_term": b.rating,
            "in_service": True,
            "angle_diff_min": -60.0,
            "angle_diff_max": 60.0,
        }
    loads: dict[str, dict] = {
        bus_load.zone: {
            "bus": bus_load.zone,
            "in_service": True,
            "p_load": {"data_type": "time_series", "values": bus_load.p_load},
        }
        for bus_load in net.loads
    }
    data = {
        "elements": {"bus": buses, "generator": generators, "branch": branches, "load": loads},
        "system": {
            "baseMVA": net.baseMVA,
            "reference_bus": net.reference_zone,
            "reference_bus_angle": 0.0,
            "time_keys": time_keys,
            "time_period_length_minutes": 60,
        },
    }
    return ModelData(data)


def model_data_for_hour(md: ModelData, time_key: str) -> ModelData:
    hour_md = md.clone_at_time(time_key)
    hour_md.data["system"]["time_keys"] = md.data["system"]["time_keys"]
    return hour_md


def enforce_commitment(
    net: NodalNetwork, hour_md: ModelData, commitment: dict[str, float], t: int
) -> ModelData:
    bounds = {g.name: (g.p_min, g.p_max) for g in net.generators}
    for name, gen in dict(hour_md.elements("generator")).items():
        if commitment[name] == 0:
            gen["p_min"] = 0.0
            gen["p_max"] = 0.0
        else:
            pmin, pmax = bounds[name]
            gen["p_min"] = pmin
            gen["p_max"] = pmax
    return hour_md
