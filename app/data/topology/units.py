from __future__ import annotations


def reactance_pu(ohm: float, kv: float, base_mva: float = 100.0) -> float:
    """Convert Ω (total line reactance) to per-unit on baseMVA at the line's kV."""
    if kv <= 0:
        return 0.0
    return ohm * base_mva / (kv * kv)
