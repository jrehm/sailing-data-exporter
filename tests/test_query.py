"""_query_series: Flux string construction, record parsing, error handling."""

import logging

import app


def _run_query(client, *, measurement="navigation.speedOverGround", field="value",
               source=None, convert=None, interval="1s"):
    """Call _query_series with sensible defaults and return (result, flux)."""
    convert = convert or app._scale(app._MPS_TO_KTS)
    result = app._query_series(
        client, measurement, field, source, convert,
        start="2026-08-01T00:00:00Z", stop="2026-08-01T01:00:00Z", interval=interval,
    )
    flux = client.query_api_.queries[-1]
    return result, flux


def _table(records):
    return type("T", (), {"records": records})()


def _rec(ts, value):
    return type("R", (), {"get_time": lambda self: ts, "get_value": lambda self: value})()


def test_flux_has_bucket_range_and_filters(fake_client):
    _, flux = _run_query(fake_client, measurement="navigation.speedOverGround")
    assert 'from(bucket: "signalk")' in flux
    assert "range(start: 2026-08-01T00:00:00Z, stop: 2026-08-01T01:00:00Z)" in flux
    assert 'r["_measurement"] == "navigation.speedOverGround"' in flux
    assert 'r["_field"] == "value"' in flux
    assert 'keep(columns: ["_time", "_value"])' in flux


def test_flux_no_source_filter_when_none(fake_client):
    _, flux = _run_query(fake_client, source=None)
    assert 'r["source"]' not in flux


def test_flux_source_filter_when_given(fake_client):
    _, flux = _run_query(fake_client, source="n2k-can0.10")
    assert 'r["source"] == "n2k-can0.10"' in flux


def test_flux_no_aggregate_for_1s(fake_client):
    _, flux = _run_query(fake_client, interval="1s")
    assert "aggregateWindow" not in flux


def test_flux_aggregate_for_coarser_interval(fake_client):
    _, flux = _run_query(fake_client, interval="10s")
    assert "aggregateWindow(every: 10s, fn: mean, createEmpty: false)" in flux


def test_parses_records_and_converts(fake_client, utc_timestamp):
    fake_client.query_api_.responder = lambda flux: [
        _table([_rec(utc_timestamp(2026, 8, 1, 0, 0, 0), 10.0)]),
    ]
    result, _ = _run_query(fake_client)
    assert result == {"2026-08-01T00:00:00Z": "19.4384"}  # 10 m/s -> kts


def test_skips_none_values(fake_client, utc_timestamp):
    fake_client.query_api_.responder = lambda flux: [
        _table([
            _rec(utc_timestamp(2026, 8, 1, 0, 0, 0), None),
            _rec(utc_timestamp(2026, 8, 1, 0, 0, 5), 5.0),
        ]),
    ]
    result, _ = _run_query(fake_client)
    assert result == {"2026-08-01T00:00:05Z": "9.7192"}


def test_first_value_wins_per_timestamp(fake_client, utc_timestamp):
    """Two tables reporting the same timestamp — first one wins."""
    fake_client.query_api_.responder = lambda flux: [
        _table([_rec(utc_timestamp(2026, 8, 1, 0, 0, 0), 10.0)]),
        _table([_rec(utc_timestamp(2026, 8, 1, 0, 0, 0), 99.0)]),
    ]
    result, _ = _run_query(fake_client)
    assert result == {"2026-08-01T00:00:00Z": "19.4384"}


def test_convert_failure_falls_back_to_raw(fake_client, utc_timestamp):
    fake_client.query_api_.responder = lambda flux: [
        _table([_rec(utc_timestamp(2026, 8, 1, 0, 0, 0), "not-a-number")]),
    ]
    result, _ = _run_query(fake_client, convert=app._IDENTITY)
    assert result == {"2026-08-01T00:00:00Z": "not-a-number"}


def test_query_exception_returns_empty_and_logs(fake_client, caplog):
    def boom(flux):
        raise RuntimeError("connection refused")

    fake_client.query_api_.responder = boom
    with caplog.at_level(logging.WARNING, logger="app"):
        result, _ = _run_query(fake_client, measurement="env.depth")
    assert result == {}
    assert any("env.depth" in r.message for r in caplog.records)
