from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from app.pipeline import delta_i

DD = str(Path(__file__).parent / "fixtures" / "xm_smoke")


def _hours(offers_by_hour):
    return [set(h) for h in offers_by_hour]


def _scenario(shift, n=24):
    """Offers A=100k, B=300k, C=700k COP/MWh; the real price is the offer of the
    marginal unit plus a constant `shift` (as in CREG's MPO + dI)."""
    offers = pd.Series({"A": 100_000.0, "B": 300_000.0, "C": 700_000.0})
    marginal = np.array([100_000.0, 300_000.0, 700_000.0] * 8)[:n]
    spot = marginal + shift
    available = _hours([{"A", "B", "C"}] * n)
    return spot, offers, available


def test_recovers_a_constant_daily_shift():
    spot, offers, available = _scenario(12_000.0)
    shift, matched = delta_i.estimate_delta_i(spot, offers, available)
    assert shift == 12_000.0 and matched == 24


def test_zero_shift_when_price_equals_offers_and_ties_prefer_smaller():
    spot, offers, available = _scenario(0.0)
    assert delta_i.estimate_delta_i(spot, offers, available) == (0.0, 24)


def test_unavailable_units_cannot_explain_the_price():
    spot, offers, _ = _scenario(0.0)
    none_available = _hours([set()] * 24)
    shift, matched = delta_i.estimate_delta_i(spot, offers, none_available)
    assert matched == 0


def test_shift_is_bounded_by_max_delta():
    spot, offers, available = _scenario(50_000.0)  # above MAX_DELTA
    shift, matched = delta_i.estimate_delta_i(spot, offers, available)
    assert shift == 0.0 and matched < 24


def test_metrics_on_fixture_remove_the_shift_from_the_error():
    # fixture: bolsa 200 COP/kWh = 200_000 COP/MWh, offers 150k/180k -> dI = 20_000 (marginal 180k)
    spot = np.full(24, 200_000.0)
    model = np.full(24, 180_000.0)  # the model finds the right marginal unit but has no dI
    out = delta_i.delta_i_metrics(date(2024, 4, 18), spot, model, data_dir=DD)
    assert out["delta_i"] == 20_000.0 and out["delta_i_hours_matched"] == 24.0
    assert (
        out["mae_ex_delta"] == 0.0 and out["bias_ex_delta"] == 0.0 and out["wape_ex_delta"] == 0.0
    )


def test_metrics_empty_when_reference_is_not_the_bolsa_price():
    imar_like = np.full(24, 150_000.0)  # not the PrecBolsNaci series
    assert delta_i.delta_i_metrics(date(2024, 4, 18), imar_like, imar_like, data_dir=DD) == {}


def test_metrics_empty_without_data_for_the_date():
    spot = np.full(24, 200_000.0)
    assert delta_i.delta_i_metrics(date(2019, 1, 1), spot, spot, data_dir=DD) == {}
