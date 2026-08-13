"""Shared fixtures: a fake InfluxDB client that records queries and returns
scripted tables, plus a Flask test client wired to it."""

from __future__ import annotations

from datetime import UTC

import pytest

import app as app_module


class FakeRecord:
    """Minimal stand-in for influxdb_client's `record` object."""

    def __init__(self, timestamp, value):
        self._ts = timestamp
        self._value = value

    def get_time(self):
        return self._ts

    def get_value(self):
        return self._value


class FakeTable:
    def __init__(self, records):
        self.records = records


class FakeQueryApi:
    def __init__(self, responder=None):
        # responder(flux: str) -> list[FakeTable]
        self.responder = responder or (lambda flux: [])
        self.queries = []

    def query(self, flux):
        self.queries.append(flux)
        return self.responder(flux)


class FakeClient:
    """Stand-in for InfluxDBClient: records every Flux query sent."""

    def __init__(self, responder=None):
        self.query_api_ = FakeQueryApi(responder)
        self.closed = False

    def query_api(self):
        return self.query_api_

    def close(self):
        self.closed = True


@pytest.fixture
def fake_client(monkeypatch):
    """Install a fake InfluxDBClient into the app module.

    Returns the FakeClient so tests can inspect `client.query_api_.queries`.
    """
    client = FakeClient()
    monkeypatch.setattr(app_module, "InfluxDBClient", lambda *a, **k: client)
    return client


@pytest.fixture
def test_client():
    """Flask test client (no InfluxDB calls unless the route is exercised)."""
    app_module.app.config.update(TESTING=True)
    return app_module.app.test_client()


@pytest.fixture
def utc_timestamp():
    """Build an aware UTC datetime, e.g. utc_timestamp(2026, 8, 1, 12, 30, 0)."""
    from datetime import datetime

    def _make(*args):
        return datetime(*args, tzinfo=UTC)

    return _make
