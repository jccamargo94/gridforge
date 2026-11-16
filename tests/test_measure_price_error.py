import os

from measure_price_error import discover_ideal_runs


def _write_price(path, mtime_ns):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("datetime,ideal_marginal_price\n")
    os.utime(path, ns=(mtime_ns, mtime_ns))


def test_discover_ideal_runs_scans_nested_dirs_dedupes_by_date_and_recent_mtime(tmp_path):
    """Runs live one level deep; a date may have two runs. Keep one row per
    date, choosing the most recently modified file. Non-matching files ignored."""
    older = tmp_path / "runA" / "marginal_price-2026-08-01-ideal.csv"
    newer = tmp_path / "runB" / "marginal_price-2026-08-01-ideal.csv"
    other = tmp_path / "runC" / "marginal_price-2026-08-02-ideal.csv"
    _write_price(older, 1_000_000_000_000_000_000)
    _write_price(newer, 2_000_000_000_000_000_000)
    _write_price(other, 1_500_000_000_000_000_000)

    # non-matching files must never be discovered, even with a newer mtime
    _write_price(
        tmp_path / "runD" / "marginal_price-2026-08-01-preideal.csv", 9_000_000_000_000_000_000
    )
    _write_price(
        tmp_path / "runE" / "marginal_price-2026-08-01-ideal.csv.bak", 9_000_000_000_000_000_000
    )

    runs = discover_ideal_runs(tmp_path)

    assert len(runs) == 2
    by_date = dict(runs)
    assert set(by_date) == {"2026-08-01", "2026-08-02"}
    assert by_date["2026-08-01"] == newer
    assert by_date["2026-08-02"] == other
