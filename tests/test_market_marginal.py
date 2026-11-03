import pandas as pd

from app.market import marginal

D1, D2 = pd.Timestamp("2026-03-10"), pd.Timestamp("2026-03-11")


def _frames(spot_by_day, resources):
    """resources: (name, gen_type, price COP/kWh, dispo kW)."""
    hours = [d + pd.Timedelta(hours=h) for d in (D1, D2) for h in range(24)]
    dispo = pd.DataFrame(
        [
            {"datetime": t, "resource_name": n, "gen_type": g, "dispo": kw}
            for n, g, _, kw in resources
            for t in hours
        ]
    )
    ofertas = pd.DataFrame(
        [{"Date": d, "resource_name": n, "Value": p} for n, _, p, _ in resources for d in (D1, D2)]
    )
    spot = pd.DataFrame(
        {"datetime": hours, "precio_bolsa": [spot_by_day[t.normalize()] for t in hours]}
    )
    return dispo, ofertas, spot


RES = [
    ("HID", "HIDRAULICA", 100.0, 100_000),
    ("TER", "TERMICA", 300.0, 100_000),
]


def test_unique_candidate_gets_full_share_each_hour():
    # spot 300 COP/kWh = 300_000 COP/MWh matches TER's offer only
    out = marginal.marginal_map(*_frames({D1: 300_000.0, D2: 300_000.0}, RES))
    cells = [c for c in out["cells"] if c["hour"] == 5]
    assert cells == [{"gen_type": "TERMICA", "zone": None, "hour": 5, "share": 1.0}]
    assert out["attributed_share"] == 1.0 and out["ambiguous_share"] == 0.0


def test_share_is_fraction_of_days_and_unattributed_hours_are_counted():
    # day 2 price matches nobody (uplift too large) -> TER only half the days
    out = marginal.marginal_map(*_frames({D1: 300_000.0, D2: 500_000.0}, RES))
    (cell,) = [c for c in out["cells"] if c["hour"] == 0]
    assert cell["share"] == 0.5
    assert out["attributed_share"] == 0.5


def test_ties_split_weight_and_are_marked_ambiguous():
    res = [*RES, ("TER2", "TERMICA", 300.0, 50_000), ("SOL", "SOLAR", 300.0, 10_000)]
    out = marginal.marginal_map(*_frames({D1: 300_000.0, D2: 300_000.0}, res))
    by_tech = {c["gen_type"]: c["share"] for c in out["cells"] if c["hour"] == 0}
    assert by_tech == {"TERMICA": 0.6667, "SOLAR": 0.3333}
    assert out["ambiguous_share"] == 1.0


def test_unavailable_resource_cannot_be_marginal():
    res = [("HID", "HIDRAULICA", 100.0, 100_000), ("TER", "TERMICA", 300.0, 0)]
    out = marginal.marginal_map(*_frames({D1: 300_000.0, D2: 300_000.0}, res))
    assert out["cells"] == [] and out["attributed_share"] == 0.0


def test_tolerance_absorbs_small_uplift():
    out_tight = marginal.marginal_map(*_frames({D1: 303_000.0, D2: 303_000.0}, RES), tol=0.001)
    out_wide = marginal.marginal_map(*_frames({D1: 303_000.0, D2: 303_000.0}, RES), tol=0.02)
    assert out_tight["attributed_share"] == 0.0
    assert out_wide["attributed_share"] == 1.0


def test_zone_mapping_normalizes_names_and_reports_coverage_without_names():
    res = [("SALTO II", "HIDRAULICA", 300.0, 100_000), ("OTRA", "TERMICA", 300.0, 100_000)]
    out = marginal.marginal_map(
        *_frames({D1: 300_000.0, D2: 300_000.0}, res),
        zone_by_resource={"Salto  II": "Antioquia"},
    )
    zones = {c["gen_type"]: c["zone"] for c in out["cells"] if c["hour"] == 0}
    assert zones == {"HIDRAULICA": "Antioquia", "TERMICA": None}
    assert out["zone_mapped_share"] == 0.5
    assert "SALTO" not in str(out) and "OTRA" not in str(out)
