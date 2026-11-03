from datetime import date, timedelta

import pandas as pd

from app.market import offer_audit

DAY = date(2026, 3, 31)


def _hist(prices, resource="TERMO1", end=DAY):
    """prices: COP/kWh for the days before `end`, oldest first."""
    days = [end - timedelta(days=len(prices) - i) for i in range(len(prices))]
    return pd.DataFrame(
        {
            "Date": pd.to_datetime(days),
            "resource_name": resource,
            "Value": prices,
        }
    )


def test_in_band_offer_is_ok_and_units_are_cop_per_mwh():
    h = _hist([100, 102, 98, 101, 99, 103, 97, 100])
    out = offer_audit.audit_offer(h, "TERMO1", DAY, 100_500.0)  # COP/MWh
    assert out["status"] == "ok" and out["flag"] == "ok"
    assert out["band"]["mean_cop_mwh"] == 100_000.0  # 100 COP/kWh -> COP/MWh
    assert out["last_offer_cop_mwh"] == 100_000.0


def test_far_offer_is_alert_with_percentile_and_change():
    h = _hist([100, 102, 98, 101, 99, 103, 97, 100])
    out = offer_audit.audit_offer(h, "TERMO1", DAY, 300_000.0)
    assert out["flag"] == "alert" and out["z"] > 3
    assert out["percentile_rank"] == 100.0
    assert out["change_vs_last_pct"] == 200.0


def test_flat_history_flags_any_real_change_without_z():
    h = _hist([150] * 10)
    same = offer_audit.audit_offer(h, "TERMO1", DAY, 150_000.0)
    moved = offer_audit.audit_offer(h, "TERMO1", DAY, 160_000.0)
    assert same["flag"] == "ok" and same["z"] is None
    assert moved["flag"] == "changed" and moved["z"] is None


def test_insufficient_history_is_not_flagged():
    out = offer_audit.audit_offer(_hist([100, 100, 100]), "TERMO1", DAY, 999_000.0)
    assert out["status"] == "insufficient_history" and out["flag"] is None


def test_none_price_audits_the_published_offer():
    h = _hist([100, 102, 98, 101, 99, 103, 97, 100])
    pub = pd.DataFrame({"Date": [pd.Timestamp(DAY)], "resource_name": ["TERMO1"], "Value": [400]})
    out = offer_audit.audit_offer(pd.concat([h, pub]), "TERMO1", DAY, None)
    assert out["price_source"] == "published" and out["flag"] == "alert"


def test_none_price_without_published_offer_is_no_offer():
    out = offer_audit.audit_offer(_hist([100] * 8), "TERMO1", DAY, None)
    assert out["status"] == "no_offer"


def test_history_excludes_target_day_and_other_resources_and_old_window():
    h = pd.concat(
        [
            _hist([100, 101, 99, 100, 102, 98]),
            _hist([900] * 6, resource="OTRA"),
            _hist([5000] * 3, end=DAY - timedelta(days=200)),
        ]
    )
    out = offer_audit.audit_offer(h, "TERMO1", DAY, 100_000.0, window_days=30)
    assert out["n_history"] == 6 and out["flag"] == "ok"


def test_same_weekday_band_needs_enough_samples():
    prices = [100 + (i % 3) for i in range(60)]
    out = offer_audit.audit_offer(_hist(prices), "TERMO1", DAY, 101_000.0, window_days=60)
    assert out["same_weekday"] is not None and out["same_weekday"]["n"] >= 4


def test_flat_history_with_float_noise_is_flat_not_zscore():
    hist = pd.DataFrame(
        {"Date": pd.date_range("2026-10-01", periods=20), "resource_name": "A", "Value": 0.1234567}
    )
    same = offer_audit.audit_offer(hist, "A", date(2026, 10, 25), 0.1234567 * 1e3)
    assert same["flag"] == "ok" and same["z"] is None
    moved = offer_audit.audit_offer(hist, "A", date(2026, 10, 25), 0.1234567 * 1e3 * 1.05)
    assert moved["flag"] == "changed" and moved["z"] is None
