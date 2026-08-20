from datetime import date

import httpx
import pytest

from app.data.topology import service
from app.storage import LocalStorage


def test_recompute_demand_shares_uses_ddem_for_past_date(tmp_path, monkeypatch):
    storage = LocalStorage(str(tmp_path))
    calls = []

    def fake_fetch_demand(_storage, _d, source):
        calls.append(source)
        return "SubArea Valle,2.0,2.0\nSubArea Bogota,1.0,1.0\n"

    monkeypatch.setattr("app.data.topology.fetch.fetch_demand", fake_fetch_demand)

    shares, source = service.recompute_demand_shares(
        storage, date(2020, 1, 1), ["SubArea Valle", "SubArea Bogota"]
    )

    assert calls == ["ddem"]
    assert source == "ddem"
    assert shares["SubArea Valle"] == pytest.approx(2 / 3)
    assert shares["SubArea Bogota"] == pytest.approx(1 / 3)


def test_recompute_demand_shares_uses_pron_for_future_date(tmp_path, monkeypatch):
    storage = LocalStorage(str(tmp_path))
    calls = []

    def fake_fetch_demand(_storage, _d, source):
        calls.append(source)
        return "SubArea Valle,1,EN,1.0,0,0,0,0,0,0\nSubArea Bogota,1,EN,1.0,0,0,0,0,0,0\n"

    monkeypatch.setattr("app.data.topology.fetch.fetch_demand", fake_fetch_demand)

    _shares, source = service.recompute_demand_shares(
        storage, date(2999, 1, 1), ["SubArea Valle", "SubArea Bogota"]
    )

    assert calls == ["pron"]
    assert source == "pron"


def test_recompute_demand_shares_falls_back_when_preferred_source_missing(tmp_path, monkeypatch):
    storage = LocalStorage(str(tmp_path))
    calls = []
    responses = {
        "ddem": httpx.HTTPStatusError(
            "not published yet",
            request=httpx.Request("GET", "http://example.test"),
            response=httpx.Response(404, request=httpx.Request("GET", "http://example.test")),
        ),
        "pron": "SubArea Valle,1,EN,1.0,0,0,0,0,0,0\nSubArea Bogota,1,EN,1.0,0,0,0,0,0,0\n",
    }

    def fake_fetch_demand(_storage, _d, source):
        calls.append(source)
        result = responses[source]
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr("app.data.topology.fetch.fetch_demand", fake_fetch_demand)

    shares, source = service.recompute_demand_shares(
        storage, date(2020, 1, 1), ["SubArea Valle", "SubArea Bogota"]
    )

    assert calls == ["ddem", "pron"]
    assert source == "pron"
    assert shares["SubArea Valle"] == pytest.approx(0.5)


def test_recompute_demand_shares_raises_when_both_sources_fail(tmp_path, monkeypatch):
    storage = LocalStorage(str(tmp_path))

    def fake_fetch_demand(_storage, _d, _source):
        request = httpx.Request("GET", "http://example.test")
        response = httpx.Response(404, request=request)
        raise httpx.HTTPStatusError("not published", request=request, response=response)

    monkeypatch.setattr("app.data.topology.fetch.fetch_demand", fake_fetch_demand)

    with pytest.raises(ValueError, match="no demand data available"):
        service.recompute_demand_shares(storage, date(2020, 1, 1), ["SubArea Valle"])
