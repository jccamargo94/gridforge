# app/data/topology/parse.py
from __future__ import annotations

import math
from typing import Any

# Subareas to exclude from demand (not SIN zones to model).
EXCLUDED_SUBAREAS = {"Ecuador138", "Ecuador230", "Total"}


def _data(payload: Any) -> list[Any]:
    """Normalize the {header, data} vs {data: [...]} envelope."""
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"]
    return payload


def parse_substations(payload: Any) -> list[dict]:
    subs = []
    for row in _data(payload):
        levels = row.get("voltageLevel") or []
        base_kv = max((float(v) for v in levels), default=230.0)
        subs.append(
            {
                "name": row["elementName"],
                "base_kv": base_kv,
                "subarea": row.get("subAreaName") or "",
                "latitude": row.get("latitude"),
                "longitude": row.get("longitude"),
            }
        )
    return subs


def parse_lines(payload: Any) -> list[dict]:
    lines = []
    for row in _data(payload):
        sub = row.get("subStation") or ""
        parts = sub.split(" - ", 1)
        from_zone = parts[0].strip() if parts else sub.strip()
        to_zone = parts[1].strip() if len(parts) > 1 else ""
        kv = float(row.get("ratedVoltage") or 0.0)
        thermal_a = row.get("thermalLimit")
        if thermal_a is None:
            thermal_a = row.get("ratedCurrent") or 0.0
        rating = float(thermal_a) * kv * math.sqrt(3) / 1000.0
        # Reactance comes per-km (Ω/km). Total Ω = Σ (X1_i × length_i) over tramos.
        # Fallback: use row-level length if a tramo has no length of its own.
        row_length = float(row.get("length") or 0.0)
        reactance_ohm = 0.0
        type_lines = row.get("typeLines") or []
        for tl in type_lines:
            x_km = float(tl.get("reactance") or 0.0)
            seg_len = float(tl.get("length") or row_length)
            reactance_ohm += x_km * seg_len
        lines.append(
            {
                "name": row.get("name") or sub,
                "from_zone": from_zone,
                "to_zone": to_zone,
                "reactance_ohm": reactance_ohm,
                "kv": kv,
                "rating": rating,
                "subarea": row.get("subArea") or "",
            }
        )
    return lines


def parse_map_lines(payload: Any) -> list[dict]:
    """Parse TransmissionMap/getLines GeoJSON into structured line endpoints.

    Only identity fields (sub1/sub2 are exact substation elementName strings,
    no free-text split needed). Electrical parameters aren't in this payload;
    the build layer cross-references them from parse_lines() output by name.
    """
    lines = []
    for feature in _data(payload):
        props = feature["properties"]
        lines.append(
            {
                "name": props["nameLine"],
                "sub1": props["sub1"],
                "sub2": props["sub2"],
            }
        )
    return lines


def parse_generators(
    capacity_payload: Any,
    thermal_payload: Any,
    hydro_payload: Any,
    solar_payload: Any,
    wind_payload: Any,
) -> list[dict]:
    # Capacity catalog is the authoritative per-element list with subarea.
    # Walk its nested dataReport[] structure to collect (name, capacity, subarea).
    gens: list[dict] = []
    capacity_root = _data(capacity_payload)
    if isinstance(capacity_root, dict):
        capacity_root = capacity_root.get("dataReport")
    for plant_group in capacity_root if isinstance(capacity_root, list) else []:
        for dispatched in plant_group.get("dispatchedType", []):
            for gtype in dispatched.get("generatorTypes", []):
                for element in gtype.get("elements", []):
                    cap = float(element.get("netEffectiveCapacity") or 0.0)
                    if cap <= 0:
                        continue
                    gens.append(
                        {
                            "name": element["elementName"],
                            "capacity": cap,
                            "fuel": _fuel_for(element, gtype),
                            "marginal_cost": _cost_for(element, gtype),
                            "subarea": element.get("subArea") or "",
                            "latitude": None,
                            "longitude": None,
                        }
                    )
    return gens


def _fuel_for(element: dict, gtype: dict) -> str:
    name = (gtype.get("name") or "").lower()
    if "hidráulica" in name or "hidraulica" in name:
        return "hydro"
    if "solar" in name:
        return "solar"
    if "eólica" in name or "eolica" in name or "viento" in name:
        return "wind"
    return "thermal"


def _cost_for(element: dict, gtype: dict) -> float:
    # Marginal cost: thermal uses heat-rate × fuel price (documented fallback);
    # hydro/solar/wind use 0.0 (zero fuel cost).
    fuel = _fuel_for(element, gtype)
    if fuel != "thermal":
        return 0.0
    # Documented fallback table (USD/MWh); refined per-plant via getAllFuel heatRate.
    return 80.0


def parse_demand(text: str, source: str) -> dict[str, list[float]]:
    demand: dict[str, list[float]] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        name, _, rest = line.partition(",")
        name = name.strip().strip('"')
        if name in EXCLUDED_SUBAREAS or name.startswith("Venezuela_"):
            continue
        if source == "ddem":
            values = [float(x) for x in rest.split(",") if x.strip()]
            demand[name] = values
        else:
            # PRON_AREAS: Sub<nombre>,<hora>,<EN|POT>,<7 daily values>
            hour, _, values_text = rest.partition(",")
            if not values_text.strip():
                continue
            values = [float(x) for x in values_text.split(",") if x.strip()]
            demand.setdefault(name, [0.0] * 24)
            h = int(hour.strip())
            if 1 <= h <= 24:
                demand[name][h - 1] = values[0]  # first daily value (energy EN)
    return demand
