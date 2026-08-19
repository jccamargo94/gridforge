# tests/test_topology_fetch.py
import httpx

from app.data.topology import fetch
from app.storage import LocalStorage


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}", request=httpx.Request("GET", ""), response=None
            )


def test_fetch_json_passes_paratec_headers(monkeypatch):
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return _FakeResponse({"ok": True})

    monkeypatch.setattr(httpx, "get", fake_get)

    result = fetch.fetch_json("https://example.com/x", headers=fetch.PARATEC_HEADERS)
    assert result == {"ok": True}
    url, kwargs = calls[0]
    assert kwargs["headers"] == fetch.PARATEC_HEADERS


def test_fetch_all_caches_raw_json(tmp_path, monkeypatch):
    storage = LocalStorage(str(tmp_path))
    hits = {"n": 0}

    def fake_get(url, **kwargs):
        hits["n"] += 1
        name = url.rsplit("/", 1)[-1].replace("get", "data")
        return _FakeResponse({"header": {"code": 200}, "data": [{"from": name}]})

    monkeypatch.setattr(httpx, "get", fake_get)

    first = fetch.fetch_all(storage)
    second = fetch.fetch_all(storage)  # should be cache no-op

    assert hits["n"] > 0
    assert hits["n"] == len(fetch.ENDPOINTS)  # second call made no HTTP request
    assert first == second
