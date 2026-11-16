from datetime import date

import pandas as pd
import pytest

from app.pipeline.thermal_fix import apply_thermal_real_generation

T0 = pd.Timestamp("2024-04-18")
HOURS = [T0 + pd.Timedelta(hours=h) for h in range(3)]


def _gene(rows):
    return pd.DataFrame(rows, columns=["datetime", "resource_name", "gen"])


def _spot(values):
    """Hourly bolsa spot price (COP/MWh) aligned to HOURS."""
    return pd.Series(values, index=HOURS, dtype=float)


def _inputs():
    pmax = {(g, t): 100.0 for g in ("TERMO A", "TERMO B", "BARATA") for t in HOURS}
    beta = pd.Series({"TERMO A": 300_000.0, "TERMO B": 400_000.0, "BARATA": 50_000.0})
    demand = pd.Series([500.0, 500.0, 500.0], index=HOURS)
    return pmax, demand, beta


def test_residual_subtracts_from_demand_and_pmax():
    pmax, demand, beta = _inputs()
    gene = _gene([(t, "termo a", 60.0) for t in HOURS] + [(HOURS[0], "TERMO B", 150.0)])
    # Both thermals are out of merit: beta 300k / 400k exceeds spot 100k.
    new_pmax, new_demand, fixed = apply_thermal_real_generation(
        pmax, demand, beta, ["TERMO A", "TERMO B"], gene, spot=_spot([100_000.0] * 3)
    )
    assert new_pmax[("TERMO A", HOURS[0])] == pytest.approx(40.0)
    # TERMO B real gen 150 > Pmax 100 -> fixed min(gen, Pmax) = 100
    assert new_pmax[("TERMO B", HOURS[0])] == 0.0
    assert new_demand[HOURS[0]] == pytest.approx(500 - 60 - 100)
    assert new_demand[HOURS[1]] == pytest.approx(500 - 60)
    assert fixed == {"TERMO A": pytest.approx(180.0), "TERMO B": pytest.approx(100.0)}
    # original inputs untouched
    assert pmax[("TERMO A", HOURS[0])] == 100.0 and demand[HOURS[0]] == 500.0


def test_cheap_or_unknown_plants_not_fixed():
    pmax, demand, beta = _inputs()
    gene = _gene([(t, "BARATA", 80.0) for t in HOURS] + [(t, "OTRA", 50.0) for t in HOURS])
    new_pmax, new_demand, fixed = apply_thermal_real_generation(
        pmax, demand, beta, ["BARATA", "OTRA"], gene, spot=_spot([100_000.0] * 3)
    )
    assert fixed == {} and new_pmax == pmax
    assert list(new_demand) == list(demand)


def test_dict_demand_preserved_and_floor_zero():
    pmax, demand, beta = _inputs()
    gene = _gene([(t, "TERMO A", 100.0) for t in HOURS])
    _, new_demand, _ = apply_thermal_real_generation(
        pmax,
        {t: 30.0 for t in HOURS},
        beta,
        ["TERMO A"],
        gene,
        spot=_spot([100_000.0] * 3),
    )
    assert isinstance(new_demand, dict) and all(v == 0.0 for v in new_demand.values())


def test_in_merit_thermal_not_fixed_when_beta_below_spot():
    """A thermal whose offer is below the real spot sets the margin: keep its availability."""
    pmax, demand, beta = _inputs()
    gene = _gene([(t, "TERMO A", 60.0) for t in HOURS])
    # TERMO A beta 300k < spot 900k at every hour -> in merit, must NOT be fixed.
    new_pmax, new_demand, fixed = apply_thermal_real_generation(
        pmax, demand, beta, ["TERMO A"], gene, spot=_spot([900_000.0] * 3)
    )
    assert fixed == {}
    assert new_pmax == pmax
    assert list(new_demand) == list(demand)


def test_out_of_merit_thermal_fixed_when_beta_above_spot():
    """Only the out-of-merit thermal's real generation is subtracted from Pmax and demand."""
    pmax, demand, beta = _inputs()
    gene = _gene([(t, "TERMO B", 40.0) for t in HOURS])
    # TERMO B beta 400k > spot 200k at every hour -> out of merit, must be fixed.
    new_pmax, new_demand, fixed = apply_thermal_real_generation(
        pmax, demand, beta, ["TERMO B"], gene, spot=_spot([200_000.0] * 3)
    )
    assert new_pmax[("TERMO B", HOURS[0])] == pytest.approx(60.0)
    assert new_pmax[("TERMO B", HOURS[1])] == pytest.approx(60.0)
    assert new_demand[HOURS[0]] == pytest.approx(460.0)
    assert fixed == {"TERMO B": pytest.approx(120.0)}


def test_thermal_crossing_spot_fixed_only_on_out_of_merit_hours():
    """A unit crossing spot across hours is fixed only where its offer exceeds spot."""
    pmax, demand, beta = _inputs()
    gene = _gene([(t, "TERMO A", 60.0) for t in HOURS])
    # beta 300k: hour 0 spot 200k -> out of merit; hours 1-2 spot 500k -> in merit.
    spot = _spot([200_000.0, 500_000.0, 500_000.0])
    new_pmax, new_demand, fixed = apply_thermal_real_generation(
        pmax, demand, beta, ["TERMO A"], gene, spot=spot
    )
    assert new_pmax[("TERMO A", HOURS[0])] == pytest.approx(40.0)
    assert new_pmax[("TERMO A", HOURS[1])] == pytest.approx(100.0)
    assert new_pmax[("TERMO A", HOURS[2])] == pytest.approx(100.0)
    assert new_demand[HOURS[0]] == pytest.approx(440.0)
    assert new_demand[HOURS[1]] == pytest.approx(500.0)
    assert fixed == {"TERMO A": pytest.approx(60.0)}


def test_empty_spot_fixes_nothing():
    """Missing spot data must degrade gracefully: no generation is fixed."""
    pmax, demand, beta = _inputs()
    gene = _gene([(t, "TERMO B", 40.0) for t in HOURS])
    new_pmax, new_demand, fixed = apply_thermal_real_generation(
        pmax, demand, beta, ["TERMO B"], gene, spot=pd.Series(dtype=float)
    )
    assert fixed == {}
    assert new_pmax == pmax
    assert list(new_demand) == list(demand)


def test_spot_missing_an_hour_leaves_that_hour_untouched():
    """An hour without spot data is skipped even if other hours are out of merit."""
    pmax, demand, beta = _inputs()
    gene = _gene([(t, "TERMO B", 40.0) for t in HOURS])
    spot = _spot([200_000.0, float("nan"), 200_000.0])
    new_pmax, new_demand, fixed = apply_thermal_real_generation(
        pmax, demand, beta, ["TERMO B"], gene, spot=spot
    )
    assert new_pmax[("TERMO B", HOURS[0])] == pytest.approx(60.0)
    assert new_pmax[("TERMO B", HOURS[1])] == pytest.approx(100.0)
    assert new_pmax[("TERMO B", HOURS[2])] == pytest.approx(60.0)
    assert new_demand[HOURS[1]] == pytest.approx(500.0)
    assert fixed == {"TERMO B": pytest.approx(80.0)}


def test_case_builder_rejects_non_ideal():
    from app.pipeline.case_builder import build_case
    from app.schemas import DispatchCase, DispatchLevel, InputPack, InputSource

    fx = str(__import__("pathlib").Path(__file__).parent / "fixtures" / "xm_smoke")
    case = DispatchCase(
        dispatch_date=date(2024, 4, 18), level=DispatchLevel.preideal, thermal_real_generation=True
    )
    inputs = InputPack(dispatch_date=date(2024, 4, 18), source=InputSource.historical, data_dir=fx)
    with pytest.raises(ValueError, match="solo aplica al nivel ideal"):
        build_case(case, inputs)


def test_build_case_ideal_applies_thermal_real_generation(monkeypatch):
    """With a low real spot the thermal is out of merit and its real generation is fixed."""
    import app.pipeline.case_builder as cb
    from app.schemas import DispatchCase, DispatchLevel, InputPack, InputSource

    fx = str(__import__("pathlib").Path(__file__).parent / "fixtures" / "xm_smoke")
    day = date(2024, 4, 18)
    inputs = InputPack(dispatch_date=day, source=InputSource.historical, data_dir=fx)
    hours = [pd.Timestamp(day) + pd.Timedelta(hours=h) for h in range(24)]
    # Raw CSV is COP/kWh; the loader scales by 1e3. 50 -> 50_000 COP/MWh,
    # below TERMO1's 150_000 COP/MWh offer, so the unit is out of merit.
    spot_df = pd.DataFrame({"datetime": hours, "precio_bolsa": [50.0] * 24})
    monkeypatch.setattr(cb.loaders, "load_precio_bolsa", lambda *a, **k: spot_df)

    _, base_params, _ = cb.build_case(
        DispatchCase(dispatch_date=day, level=DispatchLevel.ideal), inputs
    )
    beta = base_params["beta"]
    thermal = next(
        g for g in beta.index if beta[g] > 0 and any(k[0] == g for k in base_params["Pmax"])
    )
    gene = pd.DataFrame(
        {"datetime": hours, "resource_name": thermal, "gen": [5_000.0] * 24}  # kWh -> 5 MW
    )
    monkeypatch.setattr(cb, "ensure_gene_for_date", lambda *a, **k: None)
    monkeypatch.setattr(cb, "load_gene_day", lambda *a, **k: gene)
    case = DispatchCase(dispatch_date=day, level=DispatchLevel.ideal, thermal_real_generation=True)
    _, params, _ = cb.build_case(case, inputs)
    h0 = hours[0]
    assert params["Pmax"][(thermal, h0)] == pytest.approx(base_params["Pmax"][(thermal, h0)] - 5.0)
    assert params["demand"][h0] == pytest.approx(base_params["demand"][h0] - 5.0)


def test_build_case_ideal_respects_real_spot_when_thermal_in_merit(monkeypatch):
    """The fixture's real spot (200k) exceeds TERMO1's 150k offer: nothing is fixed."""
    import app.pipeline.case_builder as cb
    from app.schemas import DispatchCase, DispatchLevel, InputPack, InputSource

    fx = str(__import__("pathlib").Path(__file__).parent / "fixtures" / "xm_smoke")
    day = date(2024, 4, 18)
    inputs = InputPack(dispatch_date=day, source=InputSource.historical, data_dir=fx)
    _, base_params, _ = cb.build_case(
        DispatchCase(dispatch_date=day, level=DispatchLevel.ideal), inputs
    )
    beta = base_params["beta"]
    thermal = next(
        g for g in beta.index if beta[g] > 0 and any(k[0] == g for k in base_params["Pmax"])
    )
    assert beta[thermal] < 200_000.0  # fixture spot 200 COP/kWh -> 200_000 COP/MWh
    hours = [pd.Timestamp(day) + pd.Timedelta(hours=h) for h in range(24)]
    gene = pd.DataFrame({"datetime": hours, "resource_name": thermal, "gen": [5_000.0] * 24})
    monkeypatch.setattr(cb, "ensure_gene_for_date", lambda *a, **k: None)
    monkeypatch.setattr(cb, "load_gene_day", lambda *a, **k: gene)
    case = DispatchCase(dispatch_date=day, level=DispatchLevel.ideal, thermal_real_generation=True)
    _, params, _ = cb.build_case(case, inputs)
    h0 = hours[0]
    assert params["Pmax"][(thermal, h0)] == pytest.approx(base_params["Pmax"][(thermal, h0)])
    assert params["demand"][h0] == pytest.approx(base_params["demand"][h0])
