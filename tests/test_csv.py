"""_build_csv: wide-format assembly, timezone conversion, missing data."""

import csv
import io
from zoneinfo import ZoneInfo

import app


def _table(records):
    return type("T", (), {"records": records})()


def _rec(ts, value):
    return type("R", (), {"get_time": lambda self: ts, "get_value": lambda self: value})()


def _responder_for(spec):
    """spec: {measurement: {field: [(dt, raw_value), ...]}}"""
    def responder(flux):
        # Parse the measurement name out of the flux string.
        import re
        m = re.search(r'r\["_measurement"\] == "([^"]+)"', flux)
        if not m:
            return []
        meas = m.group(1)
        tables = []
        for _field, rows in spec.get(meas, {}).items():
            tables.append(_table([_rec(ts, v) for ts, v in rows]))
        return tables
    return responder


def test_wide_format_with_header_and_rows(fake_client, utc_timestamp):
    fake_client.query_api_.responder = _responder_for({
        "navigation.speedOverGround": {
            "value": [
                (utc_timestamp(2026, 8, 1, 0, 0, 0), 10.0),
                (utc_timestamp(2026, 8, 1, 0, 0, 5), 5.0),
            ],
        },
    })
    csv_text = app._build_csv(
        ["SOG"], "2026-08-01T00:00:00Z", "2026-08-01T01:00:00Z", "1s",
        ZoneInfo("UTC"),
    )
    reader = list(csv.DictReader(io.StringIO(csv_text)))
    assert reader[0]["timestamp"] == "2026-08-01 00:00:00"
    assert reader[0]["SOG"] == "19.4384"
    assert reader[1]["SOG"] == "9.7192"


def test_timestamps_converted_to_local_tz(fake_client, utc_timestamp):
    fake_client.query_api_.responder = _responder_for({
        "navigation.speedOverGround": {
            "value": [(utc_timestamp(2026, 8, 1, 12, 0, 0), 10.0)],
        },
    })
    csv_text = app._build_csv(
        ["SOG"], "2026-08-01T00:00:00Z", "2026-08-02T00:00:00Z", "1s",
        ZoneInfo("Europe/Warsaw"),  # UTC+2 in summer
    )
    reader = list(csv.DictReader(io.StringIO(csv_text)))
    assert reader[0]["timestamp"] == "2026-08-01 14:00:00"


def test_missing_series_produces_empty_cell(fake_client, utc_timestamp):
    """SOG has data but DTG query returns nothing -> empty DTG cells."""
    fake_client.query_api_.responder = _responder_for({
        "navigation.speedOverGround": {
            "value": [(utc_timestamp(2026, 8, 1, 0, 0, 0), 10.0)],
        },
    })
    csv_text = app._build_csv(
        ["SOG", "DTG"], "2026-08-01T00:00:00Z", "2026-08-01T01:00:00Z", "1s",
        ZoneInfo("UTC"),
    )
    reader = list(csv.DictReader(io.StringIO(csv_text)))
    assert len(reader) == 1
    assert reader[0]["SOG"] == "19.4384"
    assert reader[0]["DTG"] == ""


def test_merged_timestamps_sorted_and_padded(fake_client, utc_timestamp):
    """SOG and LAT have data at different times; output must be sorted and
    padded with empty cells."""
    fake_client.query_api_.responder = _responder_for({
        "navigation.speedOverGround": {
            "value": [(utc_timestamp(2026, 8, 1, 0, 0, 5), 5.0)],
        },
        "navigation.position": {
            "lat": [(utc_timestamp(2026, 8, 1, 0, 0, 0), 52.25)],
        },
    })
    csv_text = app._build_csv(
        ["LAT", "SOG"], "2026-08-01T00:00:00Z", "2026-08-01T01:00:00Z", "1s",
        ZoneInfo("UTC"),
    )
    reader = list(csv.DictReader(io.StringIO(csv_text)))
    assert [r["timestamp"] for r in reader] == [
        "2026-08-01 00:00:00", "2026-08-01 00:00:05",
    ]
    assert reader[0]["LAT"] == "52.25"
    assert reader[0]["SOG"] == ""
    assert reader[1]["LAT"] == ""
    assert reader[1]["SOG"] == "9.7192"


def test_csv_safe_applied_to_cells(fake_client, utc_timestamp):
    """Non-numeric fallback values that look like formulas get neutralized."""
    fake_client.query_api_.responder = _responder_for({
        "navigation.speedOverGround": {
            "value": [(utc_timestamp(2026, 8, 1, 0, 0, 0), "=HYPERLINK(\"http://evil\")")],
        },
    })
    csv_text = app._build_csv(
        ["SOG"], "2026-08-01T00:00:00Z", "2026-08-01T01:00:00Z", "1s",
        ZoneInfo("UTC"),
    )
    assert "'=HYPERLINK" in csv_text


def test_client_closed_after_build(fake_client, utc_timestamp):
    fake_client.query_api_.responder = _responder_for({})
    app._build_csv(
        ["SOG"], "2026-08-01T00:00:00Z", "2026-08-01T01:00:00Z", "1s",
        ZoneInfo("UTC"),
    )
    assert fake_client.closed is True


def test_client_closed_even_on_error(fake_client, utc_timestamp):
    def boom(flux):
        raise RuntimeError("down")

    fake_client.query_api_.responder = boom
    app._build_csv(
        ["SOG"], "2026-08-01T00:00:00Z", "2026-08-01T01:00:00Z", "1s",
        ZoneInfo("UTC"),
    )
    assert fake_client.closed is True
