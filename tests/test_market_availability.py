import pandas as pd

from app.market import availability as av

DAYS = pd.date_range("2026-03-01", periods=10, freq="D")


def _dispo(resource, per_day_kw, hours_zero=()):
    rows = []
    for day, kw in zip(DAYS, per_day_kw, strict=True):
        for h in range(24):
            rows.append(
                {
                    "datetime": day + pd.Timedelta(hours=h),
                    "resource_name": resource,
                    "dispo": 0 if h in hours_zero else kw,
                }
            )
    return pd.DataFrame(rows)


CAP = {"termoa": 100.0}


def _one(df, **kw):
    out = av.check_availability(df, CAP, **kw)
    return out, (out["findings"][0] if out["findings"] else None)


def test_clean_resource_has_no_findings_and_converts_kw_to_mw():
    out, f = _one(_dispo("TERMO A", [100_000] * 10))
    assert f is None and out["matched"] == 1 and out["match_rate"] == 1.0


def test_declared_above_capacity_is_flagged():
    out, f = _one(_dispo("TERMO A", [100_000] * 8 + [150_000, 150_000]))
    assert f["issues"] == ["exceeds_capacity"]
    assert f["days_over_capacity"] == 2 and f["max_ratio_to_capacity"] == 1.5


def test_tolerance_absorbs_rounding_above_capacity():
    _, f = _one(_dispo("TERMO A", [101_000] * 10))
    assert f is None


def test_persistent_low_needs_consecutive_days():
    low = [100_000, 30_000, 30_000, 30_000, 100_000, 30_000, 100_000, 30_000, 100_000, 100_000]
    _, f = _one(_dispo("TERMO A", low), min_days=3)
    assert f["issues"] == ["persistent_low"] and f["longest_low_run_days"] == 3
    _, g = _one(_dispo("TERMO A", low), min_days=4)
    assert g is None


def test_outage_days_are_counted_separately_not_as_low():
    _, f = _one(_dispo("TERMO A", [100_000] * 5 + [0, 0, 0, 0, 0]))
    assert f["issues"] == [] and f["outage_days"] == 5


def test_recurrent_zero_hours_pattern():
    _, f = _one(_dispo("TERMO A", [100_000] * 10, hours_zero=(2, 3)))
    assert f["issues"] == ["hour_pattern"] and f["zero_hours"] == [2, 3]


def test_unmatched_resources_are_reported_not_guessed():
    out = av.check_availability(_dispo("OTRA PLANTA", [100_000] * 10), CAP)
    assert out["matched"] == 0 and out["unmatched_resources"] == ["OTRA PLANTA"]


def test_capacity_by_name_normalizes_and_drops_collisions():
    gens = [
        {"name": "Termo-A", "capacity": 100},
        {"name": "SALTO", "capacity": 10},
        {"name": "salto", "capacity": 20},
    ]
    caps, collisions = av.capacity_by_name(gens)
    assert caps == {"termoa": 100.0} and collisions == ["salto"]
