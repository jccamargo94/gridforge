from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.data import loaders as loaders_mod
from app.db.models import Base, RunPlan
from app.scheduler import refresh as refresh_mod
from app.scheduler.config import SchedulerConfig

UTC = timezone.utc
CONFIG = SchedulerConfig()
DD = str(Path(__file__).parent / "fixtures" / "xm_smoke")


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


def test_refresh_tick_merges_window_and_clears_loader_cache(tmp_path):
    session = _session()
    # local precio_bolsa ends 04-17; now = 04-20 12:00 UTC -> Bogota 04-20 -> end 04-19
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
    assert fresh["datetime"].dt.date.max() == date(2024, 4, 19)
    assert len(fresh) == 192  # 8 requested days x 24h, no duplicates

    # the pull must have started at min(window edge, last_local+1) = min(04-12, 04-18)
    asked = [a for a in consult.asked if a[0] == "PrecBolsNaci"]
    assert asked and asked[0][1] == date(2024, 4, 12)
    assert asked[0][2] == date(2024, 4, 19)


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
