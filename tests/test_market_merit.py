from datetime import date

import pandas as pd
import pytest

from app.market import merit

DAY = date(2026, 3, 10)


def _frames(resources, demand_kw=500_000):
    """resources: (name, gen_type, dispo_kw, price_cop_kwh|None)."""
    hours = pd.date_range(f"{DAY} 00:00", periods=24, freq="h")
    dispo = pd.DataFrame(
        [
            {"datetime": h, "resource_name": n, "dispo": kw, "gen_type": t}
            for n, t, kw, _ in resources
            for h in hours
        ]
    )
    ofertas = pd.DataFrame(
        [
            {"Date": pd.Timestamp(DAY), "resource_name": n, "Value": p}
            for n, _, _, p in resources
            if p is not None
        ]
    )
    demanda = pd.DataFrame({"datetime": hours, "dema": [demand_kw] * 24})
    return dispo, ofertas, demanda


BASE = [
    ("HIDRO1", "HIDRAULICA", 200_000, 100.0),
    ("HIDRO2", "HIDRAULICA", 200_000, 120.0),
    ("HIDRO3", "HIDRAULICA", 100_000, 140.0),
    ("TERMO1", "TERMICA", 300_000, 300.0),
    ("TERMO2", "TERMICA", 300_000, 400.0),
]


def test_rank_and_cumulative_capacity_with_unit_conversion():
    out = merit.merit_position(*_frames(BASE), DAY, own=["TERMO1"])
    h = out["hours"][0]
    assert h["demand_mw"] == 500.0  # 500_000 kWh/h -> MW
    (mine,) = h["own"]
    assert mine["price_cop_mwh"] == 300_000.0  # 300 COP/kWh -> COP/MWh
    assert mine["capacity_mw"] == 300.0  # kW -> MW
    assert mine["rank"] == 4
    assert mine["cum_ahead_mw"] == 500.0  # 200+200+100
    assert mine["in_merit"] is False  # 500 ahead is not < 500 demand


def test_in_merit_when_demand_exceeds_capacity_ahead():
    out = merit.merit_position(*_frames(BASE, demand_kw=600_000), DAY, own=["TERMO1"])
    assert out["hours"][0]["own"][0]["in_merit"] is True


def test_clearing_price_is_offer_covering_demand():
    out = merit.merit_position(*_frames(BASE, demand_kw=600_000), DAY, own=["HIDRO1"])
    assert out["hours"][0]["clearing_price_cop_mwh"] == 300_000.0


def test_ties_share_rank_and_do_not_count_as_ahead():
    res = [("A", "TERMICA", 100_000, 50.0), ("B", "TERMICA", 100_000, 50.0)]
    out = merit.merit_position(*_frames(res), DAY, own=["A", "B"])
    ranks = {o["resource"]: (o["rank"], o["cum_ahead_mw"]) for o in out["hours"][0]["own"]}
    assert ranks == {"A": (1, 0.0), "B": (1, 0.0)}


def test_unpriced_resources_are_excluded_and_reported():
    res = [*BASE, ("SINOFERTA", "TERMICA", 50_000, None)]
    out = merit.merit_position(*_frames(res), DAY, own=["TERMO1"])
    assert out["hours"][0]["n_priced"] == 5
    assert out["unpriced_mw_avg"] == 50.0


def test_rivals_aggregated_by_tech_never_by_name_and_small_groups_hidden():
    out = merit.merit_position(*_frames(BASE), DAY, own=["TERMO1"])
    h = out["hours"][0]
    techs = {t["gen_type"]: t for t in h["market_by_tech"]}
    # HIDRAULICA has 3 rivals -> published; TERMICA has 1 rival (TERMO2) -> hidden
    assert set(techs) == {"HIDRAULICA"}
    assert techs["HIDRAULICA"]["n_resources"] == 3
    flat = str(h["market_by_tech"])
    assert "TERMO2" not in flat and "HIDRO1" not in flat
    # own plant is excluded from the market aggregate
    assert "TERMO1" not in flat


def test_small_groups_fold_into_otros_only_if_that_is_big_enough():
    res = [
        ("T1", "TERMICA", 100_000, 10.0),
        ("S1", "SOLAR", 100_000, 11.0),
        ("E1", "EOLICA", 100_000, 12.0),
        ("ME", "TERMICA", 100_000, 13.0),
    ]
    out = merit.merit_position(*_frames(res), DAY, own=["ME"])
    techs = [t["gen_type"] for t in out["hours"][0]["market_by_tech"]]
    assert techs == [merit.OTHERS]  # 3 single-resource groups fold into one k=3 bucket


def test_position_series_summarises_days():
    rows = merit.position_series(*_frames(BASE, 600_000), DAY, DAY, own=["TERMO1", "HIDRO1"])
    by = {r["resource"]: r for r in rows}
    assert by["TERMO1"]["hours_in_merit"] == 24
    assert by["HIDRO1"]["avg_rank"] == 1.0
    assert by["TERMO1"]["avg_rank_pct"] == pytest.approx(4 / 5)


def test_unknown_own_resource_yields_empty_own():
    out = merit.merit_position(*_frames(BASE), DAY, own=["NOEXISTE"])
    assert out["hours"][0]["own"] == []
