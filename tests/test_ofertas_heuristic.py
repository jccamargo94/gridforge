from datetime import date as _date

import pandas as pd

from app.data.heuristic.biddings import (
    detect_marginal_resources,
    estimate_ofertas,
    parse_mpo,
    parse_predespacho,
)


def test_parse_predespacho_reads_resource_and_24_hours():
    raw = "TERMO1,10,20,30," + ",".join(["40"] * 21) + "\nTERMO2,5,5,5," + ",".join(["5"] * 21)
    result = parse_predespacho(raw)
    assert result["TERMO1"] == [10.0, 20.0, 30.0] + [40.0] * 21
    assert result["TERMO2"] == [5.0] * 24


def test_parse_predespacho_skips_short_lines():
    raw = "TERMO1,10,20\nTERMO2," + ",".join(["5"] * 24)
    result = parse_predespacho(raw)
    assert "TERMO1" not in result
    assert result["TERMO2"] == [5.0] * 24


def test_parse_mpo_reads_mpo_row():
    raw = (
        '"Costo Marginal",' + ",".join(["990.0"] * 24) + "\n"
        '"Delta",' + ",".join(["0.0"] * 24) + "\n"
        '"MPO",' + ",".join([str(991000.0 + h) for h in range(24)])
    )
    result = parse_mpo(raw)
    assert result[0] == 991000.0
    assert result[23] == 991023.0


def test_parse_mpo_raises_when_no_mpo_row():
    raw = '"Costo Marginal",' + ",".join(["990.0"] * 24)
    try:
        parse_mpo(raw)
        assert False, "esperaba ValueError"
    except ValueError as e:
        assert "MPO" in str(e)


def test_detect_marginal_resolves_unique_candidate_hour():
    # TERMO1 a media maquina solo en la hora 5; nadie mas es candidato ahi.
    predespacho = {
        "TERMO1": [0.0] * 5 + [150.0] + [300.0] * 18,  # 150 < 300 (dispo) solo hora 5
        "TERMO2": [200.0] * 24,  # siempre al tope de su dispo (200) -> nunca candidato
    }
    dispo_declarada = {
        "TERMO1": [300.0] * 24,
        "TERMO2": [200.0] * 24,
    }
    resolved = detect_marginal_resources(predespacho, dispo_declarada)
    assert resolved == {"TERMO1": 5}


def test_detect_marginal_ambiguous_hour_resolves_nothing_for_that_hour():
    # TERMO1 y TERMO2 candidatos ambos en la hora 3, ninguno en otra hora.
    predespacho = {
        "TERMO1": [300.0] * 3 + [150.0] + [300.0] * 20,
        "TERMO2": [200.0] * 3 + [100.0] + [200.0] * 20,
    }
    dispo_declarada = {
        "TERMO1": [300.0] * 24,
        "TERMO2": [200.0] * 24,
    }
    resolved = detect_marginal_resources(predespacho, dispo_declarada)
    assert resolved == {}


def test_detect_marginal_elimination_unlocks_second_hour():
    # TERMO1 es candidato unico en hora 1 (se resuelve ahi). TERMO1 y TERMO2
    # tambien son candidatos ambos en hora 2 -- pero una vez TERMO1 se
    # resuelve por hora 1, se elimina de hora 2, dejando a TERMO2 como unico
    # candidato de hora 2, que tambien se resuelve.
    predespacho = {
        "TERMO1": [300.0, 150.0, 150.0] + [300.0] * 21,
        "TERMO2": [200.0, 200.0, 100.0] + [200.0] * 21,
    }
    dispo_declarada = {
        "TERMO1": [300.0] * 24,
        "TERMO2": [200.0] * 24,
    }
    resolved = detect_marginal_resources(predespacho, dispo_declarada)
    assert resolved == {"TERMO1": 1, "TERMO2": 2}


def test_estimate_ofertas_resolved_resource_uses_mpo_over_1e3():
    predespacho = {"TERMO1": [0.0] * 5 + [150.0] + [300.0] * 18, "TERMO2": [200.0] * 24}
    dispo_declarada = {"TERMO1": [300.0] * 24, "TERMO2": [200.0] * 24}
    mpo_by_hour = [1000.0] * 5 + [990000.0] + [1000.0] * 18
    ultimo_precio = {"TERMO1": 100.0, "TERMO2": 180.0}

    result = estimate_ofertas(
        _date(2026, 8, 11), predespacho, dispo_declarada, mpo_by_hour, ultimo_precio
    )

    row = result[result["resource_name"] == "TERMO1"].iloc[0]
    assert row["Value"] == 990.0  # resuelto hora 5 (990000 MPO / 1e3)
    assert bool(row["is_estimated"]) is True
    assert row["Date"] == pd.Timestamp(_date(2026, 8, 11))


def test_estimate_ofertas_unresolved_resource_falls_back_to_ultimo_precio():
    predespacho = {"TERMO1": [200.0] * 24}  # nunca a media maquina (== dispo todo el dia)
    dispo_declarada = {"TERMO1": [200.0] * 24}
    mpo_by_hour = [990000.0] * 24
    ultimo_precio = {"TERMO1": 150.0, "TERMO2": 180.0}  # TERMO2 ni siquiera esta en predespacho

    result = estimate_ofertas(
        _date(2026, 8, 11), predespacho, dispo_declarada, mpo_by_hour, ultimo_precio
    )

    values = result.set_index("resource_name")["Value"].to_dict()
    assert values == {"TERMO1": 150.0, "TERMO2": 180.0}
    assert result["is_estimated"].all()


def test_estimate_ofertas_empty_ultimo_precio_returns_empty_frame():
    result = estimate_ofertas(_date(2026, 8, 11), {}, {}, [0.0] * 24, {})
    assert result.empty
    assert list(result.columns) == ["Date", "resource_name", "Value", "is_estimated"]


def test_estimate_ofertas_resolved_resource_without_history_still_gets_row():
    # TERMO1 se resuelve como marginal pero nunca tuvo precio historico --
    # igual debe aparecer en el resultado, usando el MPO inferido.
    predespacho = {"TERMO1": [0.0] * 5 + [150.0] + [300.0] * 18}
    dispo_declarada = {"TERMO1": [300.0] * 24}
    mpo_by_hour = [1000.0] * 5 + [990000.0] + [1000.0] * 18
    result = estimate_ofertas(_date(2026, 8, 11), predespacho, dispo_declarada, mpo_by_hour, {})
    assert result.set_index("resource_name")["Value"].to_dict() == {"TERMO1": 990.0}
