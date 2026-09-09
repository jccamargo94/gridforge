from datetime import date, timedelta

import pandas as pd

from app.data.xm_bulk import (
    _melt_hourly,
    _merge_keyed,
    ensure_bulk_data_for_year,
    ensure_dema_come,
    ensure_dispo_come,
    ensure_dispo_declarada,
    ensure_ofertas,
    ensure_precio_bolsa,
    fetch_resource_crosswalk,
)
from app.storage import LocalStorage


def test_melt_hourly_reshapes_wide_to_long():
    raw = pd.DataFrame(
        {
            "Values_code": ["2QEK", "3ENA"],
            "Values_Hour01": [10.0, 20.0],
            "Values_Hour02": [11.0, 21.0],
            "Date": [date(2024, 4, 18), date(2024, 4, 18)],
        }
    )
    out = _melt_hourly(raw, "dispo")

    assert list(out.columns) == ["code", "datetime", "dispo"]
    assert len(out) == 4
    row = out[(out["code"] == "2QEK") & (out["datetime"] == pd.Timestamp("2024-04-18 00:00"))]
    assert row["dispo"].iloc[0] == 10.0
    row2 = out[(out["code"] == "3ENA") & (out["datetime"] == pd.Timestamp("2024-04-18 01:00"))]
    assert row2["dispo"].iloc[0] == 21.0


class _FakeConsult:
    def request_data(self, coleccion, metrica, start_date, end_date):
        assert coleccion == "ListadoRecursos"
        assert metrica == "Sistema"
        return pd.DataFrame(
            {
                "Values_Code": ["2QEK", "3ENA"],
                "Values_Name": ["SALTO II", "TERMO NORTE"],
                "Values_Type": ["HIDRAULICA", "TERMICA"],
            }
        )


def test_fetch_resource_crosswalk_renames_columns():
    out = fetch_resource_crosswalk(_FakeConsult())
    assert list(out.columns) == ["code", "resource_name", "gen_type"]
    assert out[out["code"] == "3ENA"]["gen_type"].iloc[0] == "TERMICA"


class _FakeConsultDispo:
    def __init__(self):
        self.calls = []

    def request_data(self, coleccion, metrica, start_date, end_date):
        self.calls.append((coleccion, metrica, start_date, end_date))
        return pd.DataFrame(
            {
                "Values_code": ["2QEK"],
                "Values_Hour01": [100.0],
                "Values_Hour02": [110.0],
                "Date": [date(2024, 4, 18)],
            }
        )


_CROSSWALK = pd.DataFrame(
    {"code": ["2QEK"], "resource_name": ["SALTO II"], "gen_type": ["HIDRAULICA"]}
)


def test_ensure_dispo_declarada_writes_partition_with_gen_type(tmp_path):
    consult = _FakeConsultDispo()
    ensure_dispo_declarada(2024, str(tmp_path), consult, _CROSSWALK)

    assert consult.calls == [("DispoDeclarada", "Recurso", date(2024, 1, 1), date(2024, 12, 31))]
    out = pd.read_csv(tmp_path / "dispo_declarada" / "dispo_declarada_2024.csv")
    assert list(out.columns) == ["datetime", "resource_name", "dispo", "gen_type"]
    assert out.iloc[0]["resource_name"] == "SALTO II"
    assert out.iloc[0]["gen_type"] == "HIDRAULICA"
    assert out.iloc[0]["dispo"] == 100.0


def test_ensure_dispo_declarada_is_noop_when_partition_exists(tmp_path):
    storage = LocalStorage(str(tmp_path))
    with storage.open("dispo_declarada/dispo_declarada_2024.csv", "w") as f:
        f.write("datetime,resource_name,dispo,gen_type\n")

    def _boom(*a, **kw):
        raise AssertionError("should not fetch when partition already exists")

    consult = type("C", (), {"request_data": _boom})()
    ensure_dispo_declarada(2024, str(tmp_path), consult, _CROSSWALK)


def test_ensure_dispo_come_writes_partition_without_gen_type(tmp_path):
    consult = _FakeConsultDispo()
    ensure_dispo_come(2024, str(tmp_path), consult, _CROSSWALK)

    assert consult.calls == [("DispoCome", "Recurso", date(2024, 1, 1), date(2024, 12, 31))]
    out = pd.read_csv(tmp_path / "dispo_come" / "dispo_come_2024.csv")
    assert list(out.columns) == ["datetime", "resource_name", "dispo"]


class _FakeConsultOfertas:
    def __init__(self):
        self.calls = []

    def request_data(self, coleccion, metrica, start_date, end_date):
        self.calls.append((coleccion, metrica, start_date, end_date))
        return pd.DataFrame(
            {
                "Values_code": ["2QEK"],
                "Values_Hour01": [89.657],
                "Values_Hour02": [89.657],
                "Date": [date(2024, 4, 18)],
            }
        )


def test_ensure_ofertas_writes_one_row_per_resource_per_day(tmp_path):
    consult = _FakeConsultOfertas()
    ensure_ofertas(2024, str(tmp_path), consult, _CROSSWALK)

    assert consult.calls == [("PrecOferDesp", "Recurso", date(2024, 1, 1), date(2024, 12, 31))]
    out = pd.read_csv(tmp_path / "ofertas" / "ofertas_2024.csv")
    assert list(out.columns) == ["Date", "resource_name", "Value"]
    assert len(out) == 1
    assert out.iloc[0]["resource_name"] == "SALTO II"
    assert out.iloc[0]["Value"] == 89.657


def test_ensure_ofertas_is_noop_when_partition_exists(tmp_path):
    storage = LocalStorage(str(tmp_path))
    with storage.open("ofertas/ofertas_2024.csv", "w") as f:
        f.write("Date,resource_name,Value\n")

    def _boom(*a, **kw):
        raise AssertionError("should not fetch when partition already exists")

    consult = type("C", (), {"request_data": _boom})()
    ensure_ofertas(2024, str(tmp_path), consult, _CROSSWALK)


class _FakeConsultSistema:
    def __init__(self, value):
        self.value = value

    def request_data(self, coleccion, metrica, start_date, end_date):
        return pd.DataFrame(
            {
                "Values_code": ["Sistema"],
                "Values_Hour01": [self.value],
                "Values_Hour02": [self.value],
                "Date": [date(2024, 4, 18)],
            }
        )


def test_ensure_dema_come_writes_system_series(tmp_path):
    ensure_dema_come(2024, str(tmp_path), _FakeConsultSistema(8_300_000.0))
    out = pd.read_csv(tmp_path / "demaCome" / "demaCome_2024.csv")
    assert list(out.columns) == ["datetime", "dema"]
    assert out.iloc[0]["dema"] == 8_300_000.0


def test_ensure_precio_bolsa_writes_unscaled_cop_per_kwh(tmp_path):
    ensure_precio_bolsa(2024, str(tmp_path), _FakeConsultSistema(0.2))
    out = pd.read_csv(tmp_path / "precio_bolsa" / "precio_bolsa_2024.csv")
    assert list(out.columns) == ["datetime", "precio_bolsa"]
    assert out.iloc[0]["precio_bolsa"] == 0.2  # raw COP/kWh; load_precio_bolsa applies *1e3


def test_ensure_bulk_data_for_year_is_noop_when_all_partitions_exist(tmp_path, monkeypatch):
    storage = LocalStorage(str(tmp_path))
    for name, fname in [
        ("dispo_declarada", "dispo_declarada_2024.csv"),
        ("ofertas", "ofertas_2024.csv"),
        ("demaCome", "demaCome_2024.csv"),
        ("precio_bolsa", "precio_bolsa_2024.csv"),
        ("dispo_come", "dispo_come_2024.csv"),
    ]:
        with storage.open(f"{name}/{fname}", "w") as f:
            f.write("x\n")

    def _boom(*a, **kw):
        raise AssertionError("ReadDB must not be constructed when nothing is missing")

    monkeypatch.setattr("app.data.xm_bulk.ReadDB", _boom)
    ensure_bulk_data_for_year(2024, str(tmp_path))


def test_ensure_bulk_data_for_year_fetches_missing_partitions(tmp_path, monkeypatch):
    calls = []

    class _FakeReadDB:
        def __init__(self):
            calls.append("constructed")

        def request_data(self, coleccion, metrica, start_date, end_date):
            calls.append(coleccion)
            if coleccion == "ListadoRecursos":
                return pd.DataFrame(
                    {
                        "Values_Code": ["2QEK"],
                        "Values_Name": ["SALTO II"],
                        "Values_Type": ["HIDRAULICA"],
                    }
                )
            code = "Sistema" if metrica == "Sistema" else "2QEK"
            return pd.DataFrame(
                {
                    "Values_code": [code],
                    "Values_Hour01": [1.0],
                    "Values_Hour02": [1.0],
                    "Date": [date(2024, 4, 18)],
                }
            )

    monkeypatch.setattr("app.data.xm_bulk.ReadDB", _FakeReadDB)
    ensure_bulk_data_for_year(2024, str(tmp_path))

    assert calls[0] == "constructed"
    assert (tmp_path / "dispo_declarada" / "dispo_declarada_2024.csv").exists()
    assert (tmp_path / "ofertas" / "ofertas_2024.csv").exists()
    assert (tmp_path / "demaCome" / "demaCome_2024.csv").exists()
    assert (tmp_path / "precio_bolsa" / "precio_bolsa_2024.csv").exists()
    assert (tmp_path / "dispo_come" / "dispo_come_2024.csv").exists()


def test_ensure_bulk_data_for_year_skips_crosswalk_when_not_needed(tmp_path, monkeypatch):
    calls = []

    # Create dispo_declarada/ofertas/dispo_come so they're NOT missing -> crosswalk NOT needed
    storage = LocalStorage(str(tmp_path))
    for fname in [
        "dispo_declarada_2024.csv",
        "ofertas_2024.csv",
        "dispo_come_2024.csv",
    ]:
        with storage.open(f"dispo_declarada/{fname}", "w") as f:
            f.write("x\n")
        with storage.open(f"ofertas/{fname}", "w") as f:
            f.write("x\n")
        with storage.open(f"dispo_come/{fname}", "w") as f:
            f.write("x\n")

    class _FakeReadDB:
        def __init__(self):
            calls.append("constructed")

        def request_data(self, coleccion, metrica, start_date, end_date):
            calls.append(coleccion)
            if coleccion == "ListadoRecursos":
                return pd.DataFrame(
                    {
                        "Values_Code": ["Sistema"],
                        "Values_Name": ["Sistema"],
                        "Values_Type": ["Sistema"],
                    }
                )
            return pd.DataFrame(
                {
                    "Values_code": ["Sistema"],
                    "Values_Hour01": [1.0],
                    "Values_Hour02": [1.0],
                    "Date": [date(2024, 4, 18)],
                }
            )

    monkeypatch.setattr("app.data.xm_bulk.ReadDB", _FakeReadDB)
    ensure_bulk_data_for_year(2024, str(tmp_path))

    # ReadDB should be constructed because something is missing
    assert "constructed" in calls
    # ListadoRecursos should NOT be called because only demaCome/precio_bolsa are missing
    assert "ListadoRecursos" not in calls
    # But both demaCome and precio_bolsa should be fetched and created
    assert (tmp_path / "demaCome" / "demaCome_2024.csv").exists()
    assert (tmp_path / "precio_bolsa" / "precio_bolsa_2024.csv").exists()


def test_dema_come_all_midnight_rows_have_full_datetime_format(tmp_path):
    """Regression test for pandas CSV writer mixing datetime formats.

    When all melted rows are exactly midnight (edge case from melt ordering),
    pandas' CSV writer must format them with full HH:MM:SS, not bare YYYY-MM-DD.
    This test ensures the date_format argument is present and working.
    """

    # Fake consult returns only Hour01, so all melted rows are midnight (hour_num=0).
    class _FakeConsultMidnightOnly:
        def request_data(self, coleccion, metrica, start_date, end_date):
            return pd.DataFrame(
                {
                    "Values_code": ["Sistema"],
                    "Values_Hour01": [8_300_000.0],  # Only Hour01, no Hour02+
                    "Date": [date(2024, 4, 18)],
                }
            )

    ensure_dema_come(2024, str(tmp_path), _FakeConsultMidnightOnly())

    # Read the raw CSV text to check datetime format
    csv_path = tmp_path / "demaCome" / "demaCome_2024.csv"
    with open(csv_path, "r") as f:
        content = f.read()

    lines = content.strip().split("\n")
    assert len(lines) >= 2  # header + at least 1 data row

    # Verify every datetime cell (all rows after header) has HH:MM:SS format
    for line in lines[1:]:
        # Format: datetime,dema
        # e.g., "2024-04-18 00:00:00,8300000.0"
        parts = line.split(",", 1)
        datetime_str = parts[0]
        # Must have the space and time components
        assert " " in datetime_str, f"datetime missing time part: {datetime_str}"
        # Must match YYYY-MM-DD HH:MM:SS pattern (19 chars total)
        assert len(datetime_str) == 19, f"datetime has wrong format: {datetime_str}"
        assert datetime_str.count(":") == 2, f"datetime missing colons: {datetime_str}"


def test_merge_keyed_dedupes_keep_last_and_sorts():
    existing = pd.DataFrame(
        {
            "datetime": pd.to_datetime(["2024-04-17 00:00", "2024-04-17 01:00"]),
            "resource_name": ["A", "A"],
            "dispo": [100.0, 110.0],
        }
    )
    fresh = pd.DataFrame(
        {
            "datetime": pd.to_datetime(["2024-04-17 00:00", "2024-04-18 00:00"]),
            "resource_name": ["A", "A"],
            "dispo": [999.0, 120.0],
        }
    )
    out = _merge_keyed(existing, fresh, ["datetime", "resource_name"])
    assert len(out) == 3  # 17:00 row overwritten by fresh, no duplicate
    row = out[out["datetime"] == pd.Timestamp("2024-04-17 00:00")].iloc[0]
    assert row["dispo"] == 999.0  # fresh wins on key collision
    assert (out["datetime"] == out["datetime"].sort_values()).all()


class _FakeConsultWindow:
    """ReadDB stand-in: returns two hourly days for the requested range."""

    def __init__(self, start, end):
        self.start = start
        self.end = end
        self.calls = []

    def request_data(self, coleccion, metrica, start_date, end_date):
        self.calls.append((coleccion, metrica, start_date, end_date))
        if coleccion == "ListadoRecursos":
            return pd.DataFrame(
                {
                    "Values_Code": ["2QEK", "3ENA"],
                    "Values_Name": ["SALTO II", "TERMO NORTE"],
                    "Values_Type": ["HIDRAULICA", "TERMICA"],
                }
            )
        days = [self.start + timedelta(days=i) for i in range((self.end - self.start).days + 1)]
        rows = []
        for day in days:
            rows.append({"Values_code": "2QEK", "Date": day})
            rows.append({"Values_code": "3ENA", "Date": day})
        df = pd.DataFrame(rows)
        for h in range(1, 25):
            df[f"Values_Hour{h:02d}"] = 300.0
        return df


def test_refresh_dispo_declarada_is_idempotent_and_merges(tmp_path):
    from app.data import loaders as loaders_mod
    from app.data.xm_bulk import refresh_dispo_declarada

    start, end = date(2024, 4, 17), date(2024, 4, 19)
    consult = _FakeConsultWindow(start, end)
    crosswalk = pd.DataFrame(
        {
            "code": ["2QEK", "3ENA"],
            "resource_name": ["SALTO II", "TERMO NORTE"],
            "gen_type": ["HIDRAULICA", "TERMICA"],
        }
    )
    data_dir = str(tmp_path)
    sub = tmp_path / "dispo_declarada"
    sub.mkdir()
    first_day = pd.DataFrame(
        {
            "datetime": pd.date_range("2024-04-17", periods=24, freq="h"),
            "resource_name": ["SALTO II"] * 24,
            "dispo": [100.0] * 24,
            "gen_type": ["HIDRAULICA"] * 24,
        }
    )
    first_day.to_csv(sub / "dispo_declarada_2024.csv", index=False)

    refresh_dispo_declarada(start, end, data_dir, consult, crosswalk)
    df = loaders_mod.load_dispo(data_dir, 2024)
    assert df["datetime"].dt.date.max() == date(2024, 4, 19)
    assert len(df) == 144  # 3 days x 2 resources x 24h

    # the keyed merge overwrote the stale local 04-17 value (100.0 -> 300.0)
    row = df[
        (df["datetime"].dt.date == date(2024, 4, 17)) & (df["resource_name"] == "SALTO II")
    ].iloc[0]
    assert row["dispo"] == 300.0

    # second identical pull must not duplicate rows
    refresh_dispo_declarada(start, end, data_dir, consult, crosswalk)
    df2 = loaders_mod.load_dispo(data_dir, 2024)
    assert len(df2) == 144
    assert consult.calls.count(("DispoDeclarada", "Recurso", start, end)) == 2
