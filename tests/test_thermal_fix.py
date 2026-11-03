from datetime import date

import pandas as pd
import pytest

from app.pipeline.thermal_fix import apply_thermal_real_generation

T0 = pd.Timestamp("2024-04-18")
HOURS = [T0 + pd.Timedelta(hours=h) for h in range(3)]


def _gene(rows):
    return pd.DataFrame(rows, columns=["datetime", "resource_name", "gen"])


def _inputs():
    pmax = {(g, t): 100.0 for g in ("TERMO A", "TERMO B", "BARATA") for t in HOURS}
    beta = pd.Series({"TERMO A": 300_000.0, "TERMO B": 400_000.0, "BARATA": 50_000.0})
    demand = pd.Series([500.0, 500.0, 500.0], index=HOURS)
    return pmax, demand, beta


def test_residual_subtracts_from_demand_and_pmax():
    pmax, demand, beta = _inputs()
    gene = _gene([(t, "termo a", 60.0) for t in HOURS] + [(HOURS[0], "TERMO B", 150.0)])
    new_pmax, new_demand, fixed, _ = apply_thermal_real_generation(
        pmax, demand, beta, ["TERMO A", "TERMO B"], gene
    )
    assert new_pmax[("TERMO A", HOURS[0])] == pytest.approx(40.0)
    # TERMO B real gen 150 > Pmax 100 -> se fija min(gen, Pmax) = 100
    assert new_pmax[("TERMO B", HOURS[0])] == 0.0
    assert new_demand[HOURS[0]] == pytest.approx(500 - 60 - 100)
    assert new_demand[HOURS[1]] == pytest.approx(500 - 60)
    assert fixed == {"TERMO A": pytest.approx(180.0), "TERMO B": pytest.approx(100.0)}
    # entradas originales intactas
    assert pmax[("TERMO A", HOURS[0])] == 100.0 and demand[HOURS[0]] == 500.0


def test_cheap_or_unknown_plants_not_fixed():
    pmax, demand, beta = _inputs()
    gene = _gene([(t, "BARATA", 80.0) for t in HOURS] + [(t, "OTRA", 50.0) for t in HOURS])
    new_pmax, new_demand, fixed, _ = apply_thermal_real_generation(
        pmax, demand, beta, ["BARATA", "OTRA"], gene
    )
    assert fixed == {} and new_pmax == pmax
    assert list(new_demand) == list(demand)


def test_unmatched_candidates_are_reported():
    pmax, demand, beta = _inputs()
    gene = _gene([(t, "TERMO A", 10.0) for t in HOURS])
    *_, unmatched = apply_thermal_real_generation(pmax, demand, beta, ["TERMO A", "TERMO B"], gene)
    assert unmatched == ["TERMO B"]


def test_combined_cycle_configs_subtract_demand_once():
    t = HOURS
    pmax = {(c, h): cap for c, cap in (("XCC_1", 100.0), ("XCC_2", 250.0)) for h in t}
    beta = pd.Series({"XCC_1": 500_000.0, "XCC_2": 480_000.0})
    demand = pd.Series([1000.0] * 3, index=t)
    gene = _gene([(h, "X CC", 180.0) for h in t])
    new_pmax, new_demand, fixed, unmatched = apply_thermal_real_generation(
        pmax, demand, beta, ["XCC_1", "XCC_2"], gene, cc_groups={"X CC": ["XCC_1", "XCC_2"]}
    )
    # una sola deduccion (180), no una por configuracion
    assert new_demand[t[0]] == pytest.approx(820.0)
    assert new_pmax[("XCC_1", t[0])] == 0.0 and new_pmax[("XCC_2", t[0])] == pytest.approx(70.0)
    assert fixed == {"X CC": pytest.approx(540.0)} and unmatched == []


def test_dict_demand_preserved_and_floor_zero():
    pmax, demand, beta = _inputs()
    gene = _gene([(t, "TERMO A", 100.0) for t in HOURS])
    _, new_demand, _, _ = apply_thermal_real_generation(
        pmax, {t: 30.0 for t in HOURS}, beta, ["TERMO A"], gene
    )
    assert isinstance(new_demand, dict) and all(v == 0.0 for v in new_demand.values())


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
    hours = [pd.Timestamp(day) + pd.Timedelta(hours=h) for h in range(24)]
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
