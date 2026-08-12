import pandas as pd

from app.data.loaders import (
    load_demanda,
    load_dispo,
    load_dispo_come,
    load_ofertas,
    load_precio_bolsa,
)


def _write_mini_csv(tmp_path, rel_path: str, **cols):
    """Create a minimal CSV under tmp_path so a loader can find it."""
    full = tmp_path / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(cols).to_csv(full, index=False)


def test_precio_bolsa_scaled(tmp_path):
    _write_mini_csv(
        tmp_path,
        "precio_bolsa/precio_bolsa_2024.csv",
        datetime=["2024-04-18 00:00"],
        precio_bolsa=[0.1],
    )
    out = load_precio_bolsa(str(tmp_path), 2024)
    assert abs(out["precio_bolsa"].iloc[0] - 100.0) < 1e-9


_YEAR = 2024
_HOURS = 24


def _smoke_csvs(tmp_path):
    """Write the 5 year-level CSVs so all cached loaders have something to read."""
    dd = str(tmp_path)
    _write_mini_csv(
        tmp_path,
        "dispo_declarada/dispo_declarada_2024.csv",
        datetime=[f"2024-04-18 {h:02d}:00" for h in range(_HOURS)],
        resource_name=["G1"] * _HOURS,
        dispo=[100_000] * _HOURS,
        gen_type=["TERMICA"] * _HOURS,
    )
    _write_mini_csv(
        tmp_path,
        "ofertas/ofertas_2024.csv",
        Date=["2024-04-18"],
        resource_name=["G1"],
        Value=[150],
    )
    _write_mini_csv(
        tmp_path,
        "demaCome/demaCome_2024.csv",
        datetime=[f"2024-04-18 {h:02d}:00" for h in range(_HOURS)],
        dema=[350_000] * _HOURS,
    )
    _write_mini_csv(
        tmp_path,
        "precio_bolsa/precio_bolsa_2024.csv",
        datetime=[f"2024-04-18 {h:02d}:00" for h in range(_HOURS)],
        precio_bolsa=[200] * _HOURS,
    )
    _write_mini_csv(
        tmp_path,
        "dispo_come/dispo_come_2024.csv",
        datetime=[f"2024-04-18 {h:02d}:00" for h in range(_HOURS)],
        resource_name=["G1"] * _HOURS,
        dispo=[80_000] * _HOURS,
    )
    return dd


def _clear_all_caches():
    load_dispo.cache_clear()
    load_ofertas.cache_clear()
    load_demanda.cache_clear()
    load_precio_bolsa.cache_clear()
    load_dispo_come.cache_clear()


def test_cache_hit_same_identity(tmp_path):
    """Same args return the same DataFrame object (cache hit)."""
    dd = _smoke_csvs(tmp_path)
    _clear_all_caches()

    a = load_dispo(dd, _YEAR)
    b = load_dispo(dd, _YEAR)
    assert a is b

    a = load_ofertas(dd, _YEAR)
    b = load_ofertas(dd, _YEAR)
    assert a is b

    a = load_demanda(dd, _YEAR)
    b = load_demanda(dd, _YEAR)
    assert a is b

    a = load_precio_bolsa(dd, _YEAR)
    b = load_precio_bolsa(dd, _YEAR)
    assert a is b

    a = load_dispo_come(dd, _YEAR)
    b = load_dispo_come(dd, _YEAR)
    assert a is b


def test_cache_miss_different_year(tmp_path):
    """Different year args return different DataFrame objects."""
    dd = _smoke_csvs(tmp_path)
    _write_mini_csv(
        tmp_path,
        "dispo_declarada/dispo_declarada_2025.csv",
        datetime=["2025-01-01 00:00"],
        resource_name=["G1"],
        dispo=[50_000],
        gen_type=["TERMICA"],
    )
    _clear_all_caches()

    a = load_dispo(dd, 2024)
    b = load_dispo(dd, 2025)
    assert a is not b


def test_cache_info_reflects_hits(tmp_path):
    """cache_info shows hits after repeated calls with same args."""
    dd = _smoke_csvs(tmp_path)
    _clear_all_caches()

    load_dispo(dd, _YEAR)
    info1 = load_dispo.cache_info()
    assert info1.hits == 0
    assert info1.misses == 1

    load_dispo(dd, _YEAR)
    info2 = load_dispo.cache_info()
    assert info2.hits == 1
    assert info2.misses == 1
