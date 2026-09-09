from datetime import date as _date

import pandas as pd

from app.data.heuristic.biddings import (
    detect_marginal_resources,
    ensure_ofertas_estimado,
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


def test_parse_mpo_raises_when_mpo_row_has_fewer_than_24_values():
    raw = '"MPO",' + ",".join(["1.0"] * 10)
    try:
        parse_mpo(raw)
        assert False, "esperaba ValueError"
    except ValueError as e:
        assert "24" in str(e)


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


def test_detect_marginal_skips_resource_with_incomplete_hourly_dispo():
    # dispo_declarada con menos de 24 horas para un recurso (dia parcial en
    # el CSV origen) no debe reventar con IndexError -- se descarta.
    predespacho = {"TERMO1": [150.0] * 24}
    dispo_declarada = {"TERMO1": [300.0] * 23}
    resolved = detect_marginal_resources(predespacho, dispo_declarada)
    assert resolved == {}


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


def test_detect_marginal_treats_cc_plant_as_flat_whole_plant():
    # Decision issue #36: CC plants son candidatos a nivel de planta completa
    # (Value plano), no por configuracion -- PrId/dispo frescos traen la planta
    # completa y OFEI cc_dispo esta mes-atrasada (vacia para fechas recientes).
    predespacho = {
        "FLORES 4 CC": [0.0] * 5 + [250.0] + [400.0] * 18,  # part-load solo hora 5
        "TERMO1": [300.0] * 24,  # nunca candidato
    }
    dispo_declarada = {
        "FLORES 4 CC": [400.0] * 24,
        "TERMO1": [300.0] * 24,
    }
    resolved = detect_marginal_resources(predespacho, dispo_declarada)
    assert resolved == {"FLORES 4 CC": 5}

    mpo_by_hour = [1000.0] * 5 + [990000.0] + [1000.0] * 18
    result = estimate_ofertas(
        _date(2026, 8, 11),
        predespacho,
        dispo_declarada,
        mpo_by_hour,
        {"FLORES 4 CC": 100.0, "TERMO1": 180.0},
    )
    assert result.set_index("resource_name")["Value"].to_dict() == {
        "FLORES 4 CC": 990.0,  # resuelto como planta: MPO hora 5 / 1e3
        "TERMO1": 180.0,
    }


def test_detect_marginal_sole_candidate_in_two_hours_uses_first_hour():
    # TERMO1 es candidato unico en horas 2 y 10 -- se resuelve con la primera
    # en orden de hora (0->23): eleccion arbitraria pero determinista, no un bug.
    predespacho = {
        "TERMO1": [300.0] * 2 + [150.0] + [300.0] * 7 + [150.0] + [300.0] * 13,
        "TERMO2": [200.0] * 24,
    }
    dispo_declarada = {"TERMO1": [300.0] * 24, "TERMO2": [200.0] * 24}
    assert detect_marginal_resources(predespacho, dispo_declarada) == {"TERMO1": 2}


def test_estimate_ofertas_disagreement_between_reliable_hours_keeps_one_value():
    # Mismo layout del anterior: TERMO1 candidato unico en horas 2 y 10, con
    # MPO distinto en cada hora. Solo se asigna UNA Value (gana la hora 2, la
    # mas temprana); la hora 10 queda ignorada -- nunca dos valores por recurso.
    predespacho = {
        "TERMO1": [300.0] * 2 + [150.0] + [300.0] * 7 + [150.0] + [300.0] * 13,
        "TERMO2": [200.0] * 24,
    }
    dispo_declarada = {"TERMO1": [300.0] * 24, "TERMO2": [200.0] * 24}
    mpo_by_hour = [1000.0] * 2 + [990000.0] + [1000.0] * 7 + [750000.0] + [1000.0] * 13
    result = estimate_ofertas(
        _date(2026, 8, 11), predespacho, dispo_declarada, mpo_by_hour, {"TERMO1": 100.0}
    )
    assert len(result) == 1
    assert result.iloc[0]["Value"] == 990.0


def test_detect_marginal_multiple_ambiguous_hours_resolves_nothing():
    # TERMO1 y TERMO2 candidatos ambos en horas 3 y 4, y en ningun otro lugar:
    # ninguna hora tiene un unico candidato, la eliminacion nunca aísla a nadie.
    predespacho = {
        "TERMO1": [300.0] * 3 + [150.0, 150.0] + [300.0] * 19,
        "TERMO2": [200.0] * 3 + [100.0, 100.0] + [200.0] * 19,
    }
    dispo_declarada = {"TERMO1": [300.0] * 24, "TERMO2": [200.0] * 24}
    assert detect_marginal_resources(predespacho, dispo_declarada) == {}


def test_detect_marginal_mid_day_zero_dispo_hour_resolves_other_hour():
    # Hora 12 con dispo 0 Y despacho 0 (mantenimiento): no es candidata
    # (0<0 falso) y no revienta. La hora 5 es la unica a media maquina.
    despacho = [0.0] * 5 + [150.0] + [0.0] * 6 + [0.0] + [0.0] * 11
    dispo = [300.0] * 5 + [300.0] + [300.0] * 6 + [0.0] + [300.0] * 11
    assert detect_marginal_resources({"TERMO1": despacho}, {"TERMO1": dispo}) == {"TERMO1": 5}


def test_detect_marginal_dispatch_above_zero_with_zero_dispo_not_candidate():
    # despacho=50 pero dispo=0 en la hora 12: 0<50<0 es falso, no es candidata
    # y no revienta comparando floats con un disponible nulo.
    despacho = [0.0] * 12 + [50.0] + [0.0] * 11
    dispo = [300.0] * 24
    dispo[12] = 0.0
    assert detect_marginal_resources({"TERMO1": despacho}, {"TERMO1": dispo}) == {}


def test_detect_marginal_edge_hours_resolve():
    # Las horas 0 y 23 son horas validas de resolucion (bordes del dia).
    dispo_declarada = {"TERMO1": [300.0] * 24}
    assert detect_marginal_resources({"TERMO1": [150.0] + [300.0] * 23}, dispo_declarada) == {
        "TERMO1": 0
    }
    assert detect_marginal_resources({"TERMO1": [300.0] * 23 + [150.0]}, dispo_declarada) == {
        "TERMO1": 23
    }


def test_detect_marginal_full_loading_and_zero_are_not_candidates():
    # despachado == disponible (al tope) y despachado == 0: ninguno es candidato
    # "a media maquina" (la regla es 0 < despachado < disponible).
    predespacho = {"TERMO1": [300.0] * 24, "TERMO2": [0.0] * 24}
    dispo_declarada = {"TERMO1": [300.0] * 24, "TERMO2": [200.0] * 24}
    assert detect_marginal_resources(predespacho, dispo_declarada) == {}


def test_estimate_ofertas_absent_and_never_marginal_resource_not_in_result():
    # Un recurso que nunca margina y sin precio historico no aparece en el
    # resultado; con historico, aparece solo con el ultimo precio publicado.
    predespacho = {"TERMO1": [300.0] * 24, "TERMO2": [0.0] * 24}
    dispo_declarada = {"TERMO1": [300.0] * 24, "TERMO2": [200.0] * 24}
    assert estimate_ofertas(
        _date(2026, 8, 11), predespacho, dispo_declarada, [990000.0] * 24, {}
    ).empty
    result = estimate_ofertas(
        _date(2026, 8, 11),
        predespacho,
        dispo_declarada,
        [990000.0] * 24,
        {"TERMO3": 150.0},
    )
    assert result.set_index("resource_name")["Value"].to_dict() == {"TERMO3": 150.0}


def test_estimate_ofertas_resolved_value_wins_over_ultimo_precio():
    # Recurso resuelto como marginal Y con precio historico: gana el MPO
    # inferido de la hora resuelta, no el ultimo precio publicado.
    predespacho = {"TERMO1": [0.0] * 5 + [150.0] + [300.0] * 18}
    dispo_declarada = {"TERMO1": [300.0] * 24}
    mpo_by_hour = [1000.0] * 5 + [990000.0] + [1000.0] * 18
    result = estimate_ofertas(
        _date(2026, 8, 11), predespacho, dispo_declarada, mpo_by_hour, {"TERMO1": 100.0}
    )
    assert result.set_index("resource_name")["Value"].to_dict() == {"TERMO1": 990.0}


def test_detect_marginal_real_like_all_candidate_hours_ambiguous_resolves_nothing():
    # Patron real 2026-08-02 (verificado en datos reales): 153 recursos a media
    # maquina pero todas las horas con candidatos tienen >=2 -- la eliminacion
    # nunca aísla ninguno, resolved == {} y la heuristica degrada al fallback de
    # ultimo precio. No es un bug, es el comportamiento previsto; se fija aqui.
    predespacho = {
        "A": [300.0] * 9 + [150.0, 150.0] + [300.0] * 13,
        "B": [300.0] * 9 + [100.0, 100.0] + [300.0] * 13,
        "C": [300.0] * 9 + [50.0, 50.0] + [300.0] * 13,
    }
    dispo_declarada = {"A": [300.0] * 24, "B": [300.0] * 24, "C": [300.0] * 24}
    assert detect_marginal_resources(predespacho, dispo_declarada) == {}


def _write_prid_imar(tmp_path, fecha_str="2026-08-11", mmdd="0811"):
    day_dir = tmp_path / fecha_str
    day_dir.mkdir(parents=True, exist_ok=True)
    # Nombres identicos a los del universo dispo (no ambiguos para el fuzzy
    # match) -- la robustez del match en si con nombres XM reales/ruidosos
    # queda para iterar despues (issue #35), esto prueba la orquestacion.
    (day_dir / f"PrId{mmdd}_NAL.txt").write_text(
        "TERMO1," + ",".join(["0"] * 5 + ["150"] + ["300"] * 18) + "\n"
        "TERMO2," + ",".join(["200"] * 24) + "\n",
        encoding="latin1",
    )
    mpo_row = ",".join(["1000"] * 5 + ["990000"] + ["1000"] * 18)
    (day_dir / f"iMAR{mmdd}.txt").write_text(
        f'"Costo Marginal",{mpo_row}\n"Delta",' + ",".join(["0"] * 24) + f'\n"MPO",{mpo_row}\n',
        encoding="latin1",
    )
    return day_dir


def test_ensure_ofertas_estimado_matches_names_and_caches(tmp_path):
    fecha = _date(2026, 8, 11)
    _write_prid_imar(tmp_path)

    hours = [pd.Timestamp(fecha) + pd.Timedelta(hours=h) for h in range(24)]
    dispo = pd.DataFrame(
        [
            {"resource_name": "TERMO1", "datetime": h, "dispo": 300_000.0, "gen_type": "TERMICA"}
            for h in hours
        ]
        + [
            {"resource_name": "TERMO2", "datetime": h, "dispo": 200_000.0, "gen_type": "TERMICA"}
            for h in hours
        ]
    )
    oferta_full = pd.DataFrame(
        {
            "Date": [pd.Timestamp("2026-07-30"), pd.Timestamp("2026-07-30")],
            "resource_name": ["TERMO1", "TERMO2"],
            "Value": [100.0, 180.0],
        }
    )

    result = ensure_ofertas_estimado(fecha, str(tmp_path), dispo, oferta_full)

    values = result.set_index("resource_name")["Value"].to_dict()
    assert values["TERMO1"] == 990.0  # resuelto hora 5 (990000 MPO / 1e3)
    assert values["TERMO2"] == 180.0  # nunca a media maquina -> fallback ultimo precio

    # Cachea: una segunda llamada no vuelve a leer PrId/iMAR (los borramos y
    # confirmamos que igual funciona, porque debe venir del cache).
    (tmp_path / "2026-08-11" / "PrId0811_NAL.txt").unlink()
    (tmp_path / "2026-08-11" / "iMAR0811.txt").unlink()
    cached_result = ensure_ofertas_estimado(fecha, str(tmp_path), dispo, oferta_full)
    assert cached_result.set_index("resource_name")["Value"].to_dict() == values


def test_rolling_ultimo_precio_real_wins_on_same_date_tie():
    from app.data.heuristic.biddings import _rolling_ultimo_precio

    real = pd.DataFrame(
        {
            "Date": [pd.Timestamp("2026-08-11"), pd.Timestamp("2026-08-11")],
            "resource_name": ["TERMO1", "TERMO2"],
            "Value": [150.0, 180.0],
        }
    )
    cached = pd.DataFrame(
        {
            "Date": [pd.Timestamp("2026-08-11")],
            "resource_name": ["TERMO1"],
            "Value": [990.0],
            "is_estimated": [True],
        }
    )
    out = _rolling_ultimo_precio(real, cached)
    assert out == {"TERMO1": 150.0, "TERMO2": 180.0}  # tie -> real wins


def test_rolling_ultimo_precio_estimate_carries_forward_when_newer():
    from app.data.heuristic.biddings import _rolling_ultimo_precio

    real = pd.DataFrame(
        {
            "Date": [pd.Timestamp("2026-07-30"), pd.Timestamp("2026-07-30")],
            "resource_name": ["TERMO1", "TERMO2"],
            "Value": [100.0, 180.0],
        }
    )
    cached = pd.DataFrame(
        {
            "Date": [pd.Timestamp("2026-08-11")],
            "resource_name": ["TERMO1"],
            "Value": [990.0],
            "is_estimated": [True],
        }
    )
    out = _rolling_ultimo_precio(real, cached)
    assert out == {"TERMO1": 990.0, "TERMO2": 180.0}


def test_ensure_ofertas_estimado_rolls_previous_mpo_resolution_forward(tmp_path):
    fecha1 = _date(2026, 8, 11)
    fecha2 = _date(2026, 8, 12)
    _write_prid_imar(tmp_path, "2026-08-11", "0811")  # resolves TERMO1 at hour 5

    # day 2: nobody is at part-load -> nothing resolves; only the union roll works
    day2 = tmp_path / "2026-08-12"
    day2.mkdir()
    (day2 / "PrId0812_NAL.txt").write_text(
        "TERMO1," + ",".join(["300"] * 24) + "\nTERMO2," + ",".join(["200"] * 24) + "\n",
        encoding="latin1",
    )
    mpo_row = ",".join(["1000"] * 24)
    (day2 / "iMAR0812.txt").write_text(
        f'"Costo Marginal",{mpo_row}\n"Delta",' + ",".join(["0"] * 24) + f'\n"MPO",{mpo_row}\n',
        encoding="latin1",
    )

    hours1 = [pd.Timestamp(fecha1) + pd.Timedelta(hours=h) for h in range(24)]
    hours2 = [pd.Timestamp(fecha2) + pd.Timedelta(hours=h) for h in range(24)]
    dispo1 = pd.DataFrame(
        [
            {"resource_name": "TERMO1", "datetime": h, "dispo": 300_000.0, "gen_type": "TERMICA"}
            for h in hours1
        ]
        + [
            {"resource_name": "TERMO2", "datetime": h, "dispo": 200_000.0, "gen_type": "TERMICA"}
            for h in hours1
        ]
    )
    dispo2 = pd.DataFrame(
        [
            {"resource_name": "TERMO1", "datetime": h, "dispo": 300_000.0, "gen_type": "TERMICA"}
            for h in hours2
        ]
        + [
            {"resource_name": "TERMO2", "datetime": h, "dispo": 200_000.0, "gen_type": "TERMICA"}
            for h in hours2
        ]
    )
    oferta_full = pd.DataFrame(
        {
            "Date": [pd.Timestamp("2026-07-30"), pd.Timestamp("2026-07-30")],
            "resource_name": ["TERMO1", "TERMO2"],
            "Value": [100.0, 180.0],
        }
    )

    day1 = ensure_ofertas_estimado(fecha1, str(tmp_path), dispo1, oferta_full)
    assert day1.set_index("resource_name")["Value"].to_dict()["TERMO1"] == 990.0

    # day 2 with NO marginal resolution: TERMO1 must roll the day-1 MPO estimate
    # (990.0), not fall back to the stale real 100.0 — this is the regression
    # this task fixes
    day2_result = ensure_ofertas_estimado(fecha2, str(tmp_path), dispo2, oferta_full)
    values = day2_result.set_index("resource_name")["Value"].to_dict()
    assert values["TERMO1"] == 990.0
    assert values["TERMO2"] == 180.0


def test_prune_estimated_rows_drops_covered_pairs_keeps_rest(tmp_path):
    from datetime import date

    from app.data.heuristic.biddings import prune_estimated_rows

    est_dir = tmp_path / "ofertas_estimado"
    est_dir.mkdir()
    cached = pd.DataFrame(
        [
            # April pairs the real block covers -> stale, pruned
            {
                "Date": pd.Timestamp("2026-04-05"),
                "resource_name": "TERMO1",
                "Value": 999.0,
                "is_estimated": True,
            },
            {
                "Date": pd.Timestamp("2026-04-06"),
                "resource_name": "TERMO2",
                "Value": 999.0,
                "is_estimated": True,
            },
            # April pair the real block does NOT cover -> keeps rolling
            {
                "Date": pd.Timestamp("2026-04-07"),
                "resource_name": "GHOST",
                "Value": 999.0,
                "is_estimated": True,
            },
            # May pair: outside the gated month -> untouched
            {
                "Date": pd.Timestamp("2026-05-01"),
                "resource_name": "TERMO1",
                "Value": 999.0,
                "is_estimated": True,
            },
        ]
    )
    cached.to_csv(est_dir / "ofertas_estimado_2026.csv", index=False)

    real = pd.DataFrame(
        [
            {
                "Date": pd.Timestamp("2026-04-01") + pd.Timedelta(days=i),
                "resource_name": name,
                "Value": 150.0,
            }
            for i in range(30)
            for name in ("TERMO1", "TERMO2")
        ]
    )
    pruned = prune_estimated_rows(str(tmp_path), date(2026, 4, 1), real)
    assert pruned == 2

    remaining = pd.read_csv(est_dir / "ofertas_estimado_2026.csv", parse_dates=["Date"])
    pairs = set(zip(remaining["Date"].dt.date, remaining["resource_name"]))
    assert pairs == {(date(2026, 4, 7), "GHOST"), (date(2026, 5, 1), "TERMO1")}


def test_prune_estimated_rows_noop_without_cache(tmp_path):
    from datetime import date

    from app.data.heuristic.biddings import prune_estimated_rows

    real = pd.DataFrame(
        {
            "Date": [pd.Timestamp("2026-04-01")],
            "resource_name": ["TERMO1"],
            "Value": [150.0],
        }
    )
    assert prune_estimated_rows(str(tmp_path), date(2026, 4, 1), real) == 0


def test_prune_estimated_rows_noop_when_month_not_in_cache(tmp_path):
    from datetime import date

    from app.data.heuristic.biddings import prune_estimated_rows

    est_dir = tmp_path / "ofertas_estimado"
    est_dir.mkdir()
    cached = pd.DataFrame(
        [
            {
                "Date": pd.Timestamp("2026-03-31"),
                "resource_name": "TERMO1",
                "Value": 999.0,
                "is_estimated": True,
            },
        ]
    )
    cached.to_csv(est_dir / "ofertas_estimado_2026.csv", index=False)

    real = pd.DataFrame(
        {
            "Date": [pd.Timestamp("2026-04-01")],
            "resource_name": ["TERMO1"],
            "Value": [150.0],
        }
    )
    assert prune_estimated_rows(str(tmp_path), date(2026, 4, 1), real) == 0
