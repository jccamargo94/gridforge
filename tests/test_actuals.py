from datetime import date

from app.data.actuals import (
    load_actual_bolsa,
    load_actual_dispatch,
    load_actual_price,
    load_reference_price,
)


def test_load_actual_price(tmp_path):
    (tmp_path / "2024-04-18").mkdir()
    # full 3-row iMAR format; load_actual_price reads the "MPO" row (24 values)
    mpo = ",".join(str(float(i)) for i in range(24))
    (tmp_path / "2024-04-18" / "iMAR0418.txt").write_text(
        '"Costo Marginal",' + mpo + "\n"
        '"Delta",' + ",".join("0.0" for _ in range(24)) + "\n"
        '"MPO",' + mpo + "\n"
    )
    vals = load_actual_price(date(2024, 4, 18), data_dir=str(tmp_path))
    assert len(vals) == 24
    assert vals[0] == 0.0 and vals[23] == 23.0


def test_load_actual_dispatch_reads_prid_latin1(tmp_path):
    # PrId: una fila por recurso, `nombre,v0,...,v23`. Real XM plant names
    # contain latin1-only bytes (e.g. GUATAPE with an accented E, 0xC9 in
    # latin1 -- not valid UTF-8). Must not raise, the accented character must
    # round-trip correctly, and the result is {resource: [24 MW]}.
    (tmp_path / "2024-04-18").mkdir()
    values = [float(i) for i in range(24)]
    body = ",".join(str(v) for v in values)
    (tmp_path / "2024-04-18" / "PrId0418_NAL.txt").write_bytes(
        ("GUATAP\xc9," + body + "\n").encode("latin1")
    )
    out = load_actual_dispatch(date(2024, 4, 18), data_dir=str(tmp_path))
    assert set(out) == {"GUATAPÉ"}
    assert out["GUATAPÉ"] == values


def test_load_actual_bolsa_reads_year_csv(tmp_path):
    # precio_bolsa CSV stores raw values; the loader scales to COP/MWh (x1e3).
    (tmp_path / "precio_bolsa").mkdir()
    rows = [f"2024-04-18 {h:02d}:00:00,{h + 1}" for h in range(24)]
    (tmp_path / "precio_bolsa" / "precio_bolsa_2024.csv").write_text(
        "datetime,precio_bolsa\n" + "\n".join(rows) + "\n"
    )
    vals = load_actual_bolsa(date(2024, 4, 18), data_dir=str(tmp_path))
    assert len(vals) == 24
    assert vals[0] == 1000.0 and vals[23] == 24000.0


def test_load_actual_bolsa_raises_without_rows(tmp_path):
    (tmp_path / "precio_bolsa").mkdir()
    (tmp_path / "precio_bolsa" / "precio_bolsa_2024.csv").write_text(
        "datetime,precio_bolsa\n2024-04-15 00:00:00,1\n"
    )
    try:
        load_actual_bolsa(date(2024, 4, 18), data_dir=str(tmp_path))
        raise AssertionError("expected ValueError")
    except ValueError as e:
        assert "no publicada" in str(e)


def test_load_reference_price_ideal_falls_back_to_imar(tmp_path):
    # ideal: bolsa price first, iMAR MPO as fallback; preideal: iMAR MPO.
    (tmp_path / "precio_bolsa").mkdir()
    (tmp_path / "precio_bolsa" / "precio_bolsa_2024.csv").write_text(
        "datetime,precio_bolsa\n2024-04-15 00:00:00,1\n"
    )
    (tmp_path / "2024-04-18").mkdir()
    mpo = ",".join(str(float(i)) for i in range(24))
    (tmp_path / "2024-04-18" / "iMAR0418.txt").write_text('"MPO",' + mpo + "\n")

    ideal = load_reference_price(date(2024, 4, 18), level="ideal", data_dir=str(tmp_path))
    assert len(ideal) == 24 and ideal[0] == 0.0

    preideal = load_reference_price(date(2024, 4, 18), level="preideal", data_dir=str(tmp_path))
    assert len(preideal) == 24 and preideal[0] == 0.0


def test_load_reference_price_ideal_uses_bolsa_when_available(tmp_path):
    (tmp_path / "precio_bolsa").mkdir()
    rows = [f"2024-04-18 {h:02d}:00:00,{h + 1}" for h in range(24)]
    (tmp_path / "precio_bolsa" / "precio_bolsa_2024.csv").write_text(
        "datetime,precio_bolsa\n" + "\n".join(rows) + "\n"
    )
    (tmp_path / "2024-04-18").mkdir()
    mpo = ",".join(str(float(i)) for i in range(24))
    (tmp_path / "2024-04-18" / "iMAR0418.txt").write_text('"MPO",' + mpo + "\n")

    ideal = load_reference_price(date(2024, 4, 18), level="ideal", data_dir=str(tmp_path))
    # The bolsa price (x1e3) wins over iMAR MPO when both exist.
    assert ideal[0] == 1000.0
