from datetime import date

from app.data.actuals import load_actual_dispatch, load_actual_price


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
