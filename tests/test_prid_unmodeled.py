from app.pipeline.prid_unmodeled import prid_unmodeled_mw


def _write(tmp_path, rows):
    p = tmp_path / "PrId.txt"
    p.write_text("\n".join(f"{n}," + ",".join(str(v) for v in vals) for n, vals in rows))
    return str(p)


def test_sums_only_plants_without_availability(tmp_path):
    path = _write(
        tmp_path,
        [
            ("SOLAR A", [0] * 6 + [10] * 18),
            ("PLANTA NUEVA X", [0] * 6 + [4] * 18),
            ("TOTAL", [99] * 24),
            ("NO DESPACHADA ZZ", [0] * 24),
        ],
    )
    hours, detail = prid_unmodeled_mw(path, ["SOLAR A"])
    assert list(detail) == ["PLANTA NUEVA X"]
    assert hours[0] == 0 and hours[10] == 4


def test_fuzzy_name_variant_counts_as_known(tmp_path):
    path = _write(tmp_path, [("BOSQUES SOLARES LLANOS 4", [5] * 24)])
    hours, detail = prid_unmodeled_mw(path, ["BOSQUES SOLARES DE LOS LLANOS 4"])
    assert detail == {} and sum(hours) == 0
