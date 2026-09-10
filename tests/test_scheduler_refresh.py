from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.data import loaders as loaders_mod
from app.db.models import Base, RunPlan
from app.scheduler import refresh as refresh_mod
from app.scheduler.config import SchedulerConfig

UTC = timezone.utc
CONFIG = SchedulerConfig()


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


class _FakeConsult:
    """ReadDB stand-in that answers whatever range it is asked for.

    Shape per collection matches what the real pydataxm payloads look like:
    system hourly series get one code per day, per-resource series get two
    (both codes resolve through the crosswalk), PrecOferDesp is daily.
    """

    def __init__(self, start: date, end: date):
        self.start = start
        self.end = end
        self.asked = []

    def request_data(self, coleccion, metrica, start_date, end_date):
        self.asked.append((coleccion, start_date, end_date))
        if coleccion == "ListadoRecursos":
            return pd.DataFrame(
                {
                    "Values_Code": ["2QEK", "3ENA"],
                    "Values_Name": ["SALTO II", "TERMO NORTE"],
                    "Values_Type": ["HIDRAULICA", "TERMICA"],
                }
            )
        days = [start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)]
        if coleccion == "PrecBolsNaci" or coleccion == "DemaCome":
            codes = ["2QEK"]  # Sistema series: single code, dedupe by datetime
        else:
            codes = ["2QEK", "3ENA"]  # Recurso series: both crosswalk codes
        df = pd.DataFrame([{"Values_code": code, "Date": d} for d in days for code in codes])
        for h in range(1, 25):
            df[f"Values_Hour{h:02d}"] = 300.0
        return df


def _write_year_csv(tmp_path, rel_subdir, filename, df):
    sub = tmp_path / rel_subdir
    sub.mkdir(parents=True, exist_ok=True)
    df.to_csv(sub / filename, index=False, date_format="%Y-%m-%d %H:%M:%S")


class _FakeConsultOfertasEmpty(_FakeConsult):
    """PrecOferDesp answers empty (monthly block not yet published); every
    other collection answers normally."""

    def request_data(self, coleccion, metrica, start_date, end_date):
        if coleccion == "PrecOferDesp":
            self.asked.append((coleccion, start_date, end_date))
            return pd.DataFrame()
        return super().request_data(coleccion, metrica, start_date, end_date)


def test_refresh_tick_merges_window_and_clears_loader_cache(tmp_path):
    session = _session()
    # local precio_bolsa ends 04-17; now = 04-20 12:00 UTC -> Bogota 04-20 -> end 04-21
    # (Bogota tomorrow: the D-1 lanes need rows dated D on D-1, so the request
    # window reaches through the next Bogota calendar day)
    local = pd.DataFrame(
        {
            "datetime": pd.date_range("2024-04-17", periods=24, freq="h"),
            "precio_bolsa": [200.0] * 24,
        }
    )
    _write_year_csv(tmp_path, "precio_bolsa", "precio_bolsa_2024.csv", local)

    # cache the stale frame first (must be invalidated by the tick)
    stale_max = loaders_mod.load_precio_bolsa(str(tmp_path), 2024)["datetime"].dt.date.max()
    assert stale_max == date(2024, 4, 17)

    now = datetime(2024, 4, 20, 12, 0, tzinfo=UTC)
    consult = _FakeConsult(date(2024, 4, 12), date(2024, 4, 19))
    refresh_mod.refresh_tick(
        session, now=now, config=CONFIG, data_dir=str(tmp_path), consult=consult
    )

    fresh = loaders_mod.load_precio_bolsa(str(tmp_path), 2024)
    assert fresh["datetime"].dt.date.max() == date(2024, 4, 21)
    assert len(fresh) == 192  # 8 requested days x 24h, no duplicates

    # the pull must have started at min(window edge, last_local+1) = min(04-14, 04-18)
    asked = [a for a in consult.asked if a[0] == "PrecBolsNaci"]
    assert asked and asked[0][1] == date(2024, 4, 14)
    assert asked[0][2] == date(2024, 4, 21)


def test_refresh_tick_requests_through_bogota_tomorrow(tmp_path):
    """F1: the freshness pull must reach the NEXT Bogota calendar day.

    XM returns only published rows, so requesting through tomorrow is safe —
    each series' own publication lag governs what arrives. A row of
    dispo_declarada dated D must be fetchable during D-1's window (the fresh
    daily lanes run on D-1), which the old "Bogota today - 1" end could never
    do.
    """
    session = _session()
    local = pd.DataFrame(
        {
            "datetime": pd.date_range("2024-04-17", periods=24, freq="h"),
            "precio_bolsa": [200.0] * 24,
        }
    )
    _write_year_csv(tmp_path, "precio_bolsa", "precio_bolsa_2024.csv", local)

    # 23:59 UTC == 18:59 Bogota on 04-20 (well inside D-1's window): end must be 04-21
    now = datetime(2024, 4, 20, 23, 59, tzinfo=UTC)
    consult = _FakeConsult(date(2024, 4, 14), date(2024, 4, 21))
    refresh_mod.refresh_tick(
        session, now=now, config=CONFIG, data_dir=str(tmp_path), consult=consult
    )
    asked = [a for a in consult.asked if a[0] == "PrecBolsNaci"]
    assert asked and asked[0][2] == date(2024, 4, 21)


def test_refresh_tick_pull_start_reaches_last_plus_one_when_local_stale(tmp_path):
    """Healing reach-back under the tomorrow end day.

    With the request window ending on Bogota tomorrow (04-21), a local file
    whose rows end before the window edge (04-14) must make the pull start at
    last_local + 1 (04-13), not at the bare window edge — otherwise the gap
    between the last local row and the edge would never be re-requested.
    """
    session = _session()
    local = pd.DataFrame(
        {
            "datetime": pd.date_range("2024-04-12", periods=24, freq="h"),
            "precio_bolsa": [200.0] * 24,
        }
    )
    _write_year_csv(tmp_path, "precio_bolsa", "precio_bolsa_2024.csv", local)

    now = datetime(2024, 4, 20, 12, 0, tzinfo=UTC)
    consult = _FakeConsult(date(2024, 4, 13), date(2024, 4, 21))
    refresh_mod.refresh_tick(
        session, now=now, config=CONFIG, data_dir=str(tmp_path), consult=consult
    )
    asked = [a for a in consult.asked if a[0] == "PrecBolsNaci"]
    assert asked and asked[0][1] == date(2024, 4, 13)  # last_local + 1
    assert asked[0][2] == date(2024, 4, 21)
    fresh = loaders_mod.load_precio_bolsa(str(tmp_path), 2024)
    assert fresh["datetime"].dt.date.max() == date(2024, 4, 21)


def test_refresh_tick_gate_creates_settled_rows_when_month_completes(tmp_path):
    session = _session()
    # local ofertas already covers a complete March 2024; fake serves April 1-30
    march_days = [date(2024, 3, 1) + timedelta(days=i) for i in range(31)]
    local = pd.DataFrame(
        [{"Date": pd.Timestamp(d), "resource_name": "SALTO II", "Value": 150.0} for d in march_days]
    )
    _write_year_csv(tmp_path, "ofertas", "ofertas_2024.csv", local)

    now = datetime(2024, 5, 2, 12, 0, tzinfo=UTC)  # Bogota 05-02 -> end 05-01
    # pull range for ofertas: min(05-01-7=04-24, last_local+1=04-01) = 04-01..05-01
    consult = _FakeConsult(date(2024, 4, 1), date(2024, 5, 1))
    created = refresh_mod.refresh_tick(
        session, now=now, config=CONFIG, data_dir=str(tmp_path), consult=consult
    )
    assert created == 60  # 30 days x 2 kinds for April
    kinds = {(p.kind, p.target_date) for p in session.scalars(select(RunPlan)).all()}
    assert ("preideal_settled", date(2024, 4, 30)) in kinds
    assert ("ideal_settled", date(2024, 4, 30)) in kinds
    # gate is one-shot: a second tick creates nothing new
    again = refresh_mod.refresh_tick(
        session, now=now, config=CONFIG, data_dir=str(tmp_path), consult=consult
    )
    assert again == 0


def test_refresh_tick_gate_prunes_estimates_superseded_by_real_month(tmp_path):
    """Wave-0 minor #4: the monthly gate prunes stale same-date estimates.

    Estimates cached while April had no real rows are dropped once the real
    April block covers the same (Date, resource) pair; rows for resources the
    real block does not list survive (their MPO resolution must keep rolling,
    spec section 5.2).
    """
    session = _session()
    march_days = [date(2024, 3, 1) + timedelta(days=i) for i in range(31)]
    local = pd.DataFrame(
        [{"Date": pd.Timestamp(d), "resource_name": "SALTO II", "Value": 150.0} for d in march_days]
    )
    _write_year_csv(tmp_path, "ofertas", "ofertas_2024.csv", local)

    # cache estimates for April dates (the month had no real rows yet): two
    # will be covered by the real block, one belongs to a resource the real
    # PrecOferDesp block does not list (GHOST never bids)
    est_dir = tmp_path / "ofertas_estimado"
    est_dir.mkdir()
    estimated = pd.DataFrame(
        [
            {
                "Date": pd.Timestamp("2024-04-05"),
                "resource_name": "SALTO II",
                "Value": 999.0,
                "is_estimated": True,
            },
            {
                "Date": pd.Timestamp("2024-04-06"),
                "resource_name": "TERMO NORTE",
                "Value": 999.0,
                "is_estimated": True,
            },
            {
                "Date": pd.Timestamp("2024-04-07"),
                "resource_name": "GHOST",
                "Value": 999.0,
                "is_estimated": True,
            },
        ]
    )
    estimated.to_csv(est_dir / "ofertas_estimado_2024.csv", index=False)

    now = datetime(2024, 5, 2, 12, 0, tzinfo=UTC)
    consult = _FakeConsult(date(2024, 4, 1), date(2024, 5, 1))
    created = refresh_mod.refresh_tick(
        session, now=now, config=CONFIG, data_dir=str(tmp_path), consult=consult
    )
    assert created == 60

    remaining = pd.read_csv(
        tmp_path / "ofertas_estimado" / "ofertas_estimado_2024.csv",
        parse_dates=["Date"],
    )
    pairs = set(zip(remaining["Date"].dt.date, remaining["resource_name"]))
    assert pairs == {(date(2024, 4, 7), "GHOST")}


def test_pull_start_year_rollover_reaches_back_past_window_edge(tmp_path):
    """F2 regression: first pulls of a new year have no end-year CSV yet.

    Reach-back must then consult the previous year's file (last local row
    2024-11-30), so the request starts 2024-12-01 and the December monthly
    block arrives whole. Stopping at the bare window edge (2024-12-25) would
    leave Dec 1-24 unreachable forever (_year_segments never returns to it).
    """
    nov_days = [date(2024, 11, 1) + timedelta(days=i) for i in range(30)]
    local = pd.DataFrame(
        [{"Date": pd.Timestamp(d), "resource_name": "SALTO II", "Value": 150.0} for d in nov_days]
    )
    _write_year_csv(tmp_path, "ofertas", "ofertas_2024.csv", local)

    start = refresh_mod._pull_start("ofertas", date(2025, 1, 1), CONFIG, str(tmp_path))
    assert start == date(2024, 12, 1)
    assert refresh_mod._year_segments(start, date(2025, 1, 1)) == [
        (date(2024, 12, 1), date(2024, 12, 31)),
        (date(2025, 1, 1), date(2025, 1, 1)),
    ]


def test_pull_start_rollover_without_prev_year_file_keeps_window_edge(tmp_path):
    # fresh install: neither the end-year nor the previous-year CSV exists ->
    # behavior unchanged, bare window edge
    start = refresh_mod._pull_start("ofertas", date(2025, 1, 1), CONFIG, str(tmp_path))
    assert start == date(2024, 12, 25)


def test_refresh_tick_prefetches_blobs_for_next_bogota_day_after_earliest(tmp_path, monkeypatch):
    """F1: the freshness tick must download the per-date XM blobs of the next
    Bogota day once the wall clock passes DAILY_EARLIEST — nothing else does,
    and the D-1 input gate would block forever in a clean deployment without
    it. 2024-04-20 20:05 UTC == 15:05 Bogota >= 15:00."""
    session = _session()
    fetched = []

    def _fake_ensure(dispatch_date, data_dir="data"):
        fetched.append((dispatch_date, data_dir))

    monkeypatch.setattr("app.data.download.ensure_data_for_date", _fake_ensure)
    local = pd.DataFrame(
        {
            "datetime": pd.date_range("2024-04-17", periods=24, freq="h"),
            "precio_bolsa": [200.0] * 24,
        }
    )
    _write_year_csv(tmp_path, "precio_bolsa", "precio_bolsa_2024.csv", local)

    now = datetime(2024, 4, 20, 20, 5, tzinfo=UTC)
    consult = _FakeConsult(date(2024, 4, 14), date(2024, 4, 21))
    refresh_mod.refresh_tick(
        session, now=now, config=CONFIG, data_dir=str(tmp_path), consult=consult
    )
    assert fetched == [(date(2024, 4, 21), str(tmp_path))]


def test_refresh_tick_skips_blob_prefetch_before_daily_earliest(tmp_path, monkeypatch):
    """Before DAILY_EARLIEST the blob fetch must not fire: XM may not have
    published the full D package yet, and re-downloading hourly before
    ~14:30 D-1 would churn the portal. 2024-04-20 12:00 UTC == 07:00 Bogota."""
    session = _session()
    calls = []
    monkeypatch.setattr(
        "app.data.download.ensure_data_for_date",
        lambda *a, **kw: calls.append(a),
    )
    local = pd.DataFrame(
        {
            "datetime": pd.date_range("2024-04-17", periods=24, freq="h"),
            "precio_bolsa": [200.0] * 24,
        }
    )
    _write_year_csv(tmp_path, "precio_bolsa", "precio_bolsa_2024.csv", local)

    now = datetime(2024, 4, 20, 12, 0, tzinfo=UTC)
    consult = _FakeConsult(date(2024, 4, 14), date(2024, 4, 21))
    refresh_mod.refresh_tick(
        session, now=now, config=CONFIG, data_dir=str(tmp_path), consult=consult
    )
    assert calls == []


def test_refresh_tick_blob_prefetch_honors_configured_daily_earliest(tmp_path, monkeypatch):
    """The gate must come from config, not a hardcoded 15:00."""
    session = _session()
    fetched = []

    def _fake_ensure(dispatch_date, data_dir="data"):
        fetched.append((dispatch_date, data_dir))

    monkeypatch.setattr("app.data.download.ensure_data_for_date", _fake_ensure)
    config = SchedulerConfig(daily_earliest="20:00")
    local = pd.DataFrame(
        {
            "datetime": pd.date_range("2024-04-17", periods=24, freq="h"),
            "precio_bolsa": [200.0] * 24,
        }
    )
    _write_year_csv(tmp_path, "precio_bolsa", "precio_bolsa_2024.csv", local)

    # 2024-04-21 00:30 UTC == 2024-04-20 19:30 Bogota < 20:00 -> no fetch
    consult = _FakeConsult(date(2024, 4, 14), date(2024, 4, 21))
    refresh_mod.refresh_tick(
        session,
        now=datetime(2024, 4, 21, 0, 30, tzinfo=UTC),
        config=config,
        data_dir=str(tmp_path),
        consult=consult,
    )
    assert fetched == []
    # 2024-04-21 01:30 UTC == 2024-04-20 20:30 Bogota >= 20:00 -> fetch for 04-21
    refresh_mod.refresh_tick(
        session,
        now=datetime(2024, 4, 21, 1, 30, tzinfo=UTC),
        config=config,
        data_dir=str(tmp_path),
        consult=consult,
    )
    assert fetched == [(date(2024, 4, 21), str(tmp_path))]


def test_refresh_tick_ingests_public_hourly_external_rows(tmp_path, monkeypatch):
    """SCN-HS-02-01/02: after DAILY_EARLIEST the tick upserts 24 public
    hourly rows per external series for each published Bogota day (COP/MWh
    scale — bolsa raw COP/kWh x1e3, mpo COP/MWh direct); a re-tick keeps the
    counts unchanged (no duplicates, no holes)."""
    from app.db.models import HourlySeries

    session = _session()
    local = pd.DataFrame(
        {
            "datetime": pd.date_range("2024-04-20", periods=24, freq="h"),
            "precio_bolsa": [200.0] * 24,
        }
    )
    _write_year_csv(tmp_path, "precio_bolsa", "precio_bolsa_2024.csv", local)

    # per-date iMAR blob for the ensured Bogota end day (04-21)
    blob_dir = tmp_path / "2024-04-21"
    blob_dir.mkdir(parents=True)
    mpo = '","'.join(["150000.00"] * 24)
    (blob_dir / "iMAR0421.txt").write_text(f'"MPO","{mpo}"\n')

    monkeypatch.setattr("app.data.download.ensure_data_for_date", lambda *a, **kw: None)
    # 2024-04-20 20:05 UTC == 15:05 Bogota >= DAILY_EARLIEST 15:00
    now = datetime(2024, 4, 20, 20, 5, tzinfo=UTC)
    consult = _FakeConsult(date(2024, 4, 14), date(2024, 4, 21))

    def _bogota_date(ts):
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        return ts.astimezone(ZoneInfo("America/Bogota")).date()

    def _counts_and_values():
        rows = list(session.scalars(select(HourlySeries)))
        assert all(r.tenant_id is None for r in rows)
        counts: dict = {}
        values: dict = {}
        for r in rows:
            pair = (r.series_key, _bogota_date(r.ts))
            counts[pair] = counts.get(pair, 0) + 1
            values[pair] = r.value
        return counts, values

    refresh_mod.refresh_tick(
        session, now=now, config=CONFIG, data_dir=str(tmp_path), consult=consult
    )
    counts, values = _counts_and_values()
    # merged window 04-14..04-21: every published day has a full bolsa day
    for day in [date(2024, 4, 14) + timedelta(days=i) for i in range(8)]:
        assert counts[("bolsa_tx1", day)] == 24
    # SCN-HS-04-01: raw 300 COP/kWh stored as 300000.0 COP/MWh
    assert values[("bolsa_tx1", date(2024, 4, 21))] == 300000.0
    # the ensured end-day iMAR blob yields its 24 public mpo rows
    assert counts[("mpo_xm", date(2024, 4, 21))] == 24
    assert values[("mpo_xm", date(2024, 4, 21))] == 150000.0

    # SCN-HS-02-02: a re-tick over the same period changes nothing
    refresh_mod.refresh_tick(
        session, now=now, config=CONFIG, data_dir=str(tmp_path), consult=consult
    )
    counts_again, _ = _counts_and_values()
    assert counts_again == counts


def test_refresh_tick_ingest_skips_days_without_sources(tmp_path, monkeypatch):
    """B3: ticks with no per-date iMAR blobs must not raise or invent rows —
    the bolsa year CSV created by the merge still ingests, missing mpo days
    stay gaps."""
    from app.db.models import HourlySeries

    session = _session()
    monkeypatch.setattr("app.data.download.ensure_data_for_date", lambda *a, **kw: None)
    now = datetime(2024, 4, 20, 20, 5, tzinfo=UTC)  # >= DAILY_EARLIEST
    consult = _FakeConsult(date(2024, 4, 14), date(2024, 4, 21))
    refresh_mod.refresh_tick(
        session, now=now, config=CONFIG, data_dir=str(tmp_path), consult=consult
    )
    rows = list(session.scalars(select(HourlySeries)))
    assert rows, "tick must ingest bolsa rows from the freshly merged CSV"
    assert all(r.tenant_id is None for r in rows)
    assert all(r.value == 300000.0 for r in rows if r.series_key == "bolsa_tx1")


def test_refresh_tick_survives_empty_ofertas_and_refreshes_other_series(tmp_path):
    """An unpublished PrecOferDesp monthly block (empty 0,0 payload) must not
    abort the tick: the series after ofertas in _SERIES still refresh."""
    session = _session()
    local = pd.DataFrame(
        {
            "datetime": pd.date_range("2024-04-17", periods=24, freq="h"),
            "precio_bolsa": [200.0] * 24,
        }
    )
    _write_year_csv(tmp_path, "precio_bolsa", "precio_bolsa_2024.csv", local)

    now = datetime(2024, 4, 20, 12, 0, tzinfo=UTC)
    consult = _FakeConsultOfertasEmpty(date(2024, 4, 14), date(2024, 4, 21))
    refresh_mod.refresh_tick(
        session, now=now, config=CONFIG, data_dir=str(tmp_path), consult=consult
    )

    # ofertas was a no-op (no CSV invented) ...
    assert not (tmp_path / "ofertas" / "ofertas_2024.csv").exists()
    # ... while every other series in the loop refreshed
    assert (tmp_path / "dispo_declarada" / "dispo_declarada_2024.csv").exists()
    assert (tmp_path / "demaCome" / "demaCome_2024.csv").exists()
    assert (tmp_path / "dispo_come" / "dispo_come_2024.csv").exists()
    fresh = loaders_mod.load_precio_bolsa(str(tmp_path), 2024)
    assert fresh["datetime"].dt.date.max() == date(2024, 4, 21)


def _boom(*args, **kwargs):
    raise RuntimeError("simulated refresh failure")


def test_refresh_tick_clears_loader_cache_even_when_a_refresh_raises(tmp_path, monkeypatch):
    """Minor-3 regression: a mid-batch refresh failure must not leave stale
    loader frames cached; clear_loader_caches() runs even when the tick
    propagates the exception."""
    session = _session()
    cleared = []
    monkeypatch.setattr(loaders_mod, "clear_loader_caches", lambda: cleared.append(True))
    series = [
        (name, _boom if name == "precio_bolsa" else fn, uses)
        for name, fn, uses in refresh_mod._SERIES
    ]
    monkeypatch.setattr(refresh_mod, "_SERIES", series)

    consult = _FakeConsult(date(2024, 4, 13), date(2024, 4, 19))
    with pytest.raises(RuntimeError, match="simulated refresh failure"):
        refresh_mod.refresh_tick(
            session,
            now=datetime(2024, 4, 20, 12, 0, tzinfo=UTC),
            config=CONFIG,
            data_dir=str(tmp_path),
            consult=consult,
        )
    assert cleared == [True]
