"""Flask routes: index, changelog, and the /download endpoint end-to-end."""

import io


def test_index_renders(test_client):
    resp = test_client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Sailing Data Exporter" in html
    assert "Location" in html
    assert "Performance" in html
    assert "LAT" in html
    assert "10 seconds (default)" in html


def test_changelog_renders(test_client):
    resp = test_client.get("/changelog")
    assert resp.status_code == 200
    assert "Changelog" in resp.get_data(as_text=True)


def test_download_happy_path(test_client, fake_client, utc_timestamp):
    fake_client.query_api_.responder = lambda flux: [
        type("T", (), {"records": [
            type("R", (), {
                "get_time": lambda self: utc_timestamp(2026, 8, 1, 0, 0, 0),
                "get_value": lambda self: 10.0,
            })(),
        ]})()
    ]
    resp = test_client.post("/download", data={
        "start_utc": "2026-08-01T00:00:00Z",
        "stop_utc": "2026-08-01T01:00:00Z",
        "timezone": "UTC",
        "interval": "10s",
        "measurements": ["SOG"],
    })
    assert resp.status_code == 200
    assert resp.mimetype == "text/csv"
    assert "attachment" in resp.headers["Content-Disposition"]
    assert "sailing_" in resp.headers["Content-Disposition"]
    body = resp.get_data(as_text=True)
    assert body.startswith("timestamp,SOG")
    assert "19.4384" in body


def test_download_missing_start(test_client):
    resp = test_client.post("/download", data={
        "stop_utc": "2026-08-01T01:00:00Z",
        "measurements": ["SOG"],
    })
    assert resp.status_code == 400


def test_download_missing_stop(test_client):
    resp = test_client.post("/download", data={
        "start_utc": "2026-08-01T00:00:00Z",
        "measurements": ["SOG"],
    })
    assert resp.status_code == 400


def test_download_no_measurements(test_client):
    resp = test_client.post("/download", data={
        "start_utc": "2026-08-01T00:00:00Z",
        "stop_utc": "2026-08-01T01:00:00Z",
        "measurements": [],
    })
    assert resp.status_code == 400


def test_download_invalid_date(test_client):
    resp = test_client.post("/download", data={
        "start_utc": "not-a-date",
        "stop_utc": "2026-08-01T01:00:00Z",
        "measurements": ["SOG"],
    })
    assert resp.status_code == 400


def test_download_stop_before_start(test_client):
    resp = test_client.post("/download", data={
        "start_utc": "2026-08-01T01:00:00Z",
        "stop_utc": "2026-08-01T00:00:00Z",
        "measurements": ["SOG"],
    })
    assert resp.status_code == 400


def test_download_invalid_interval_falls_back_to_10s(test_client, fake_client, utc_timestamp):
    fake_client.query_api_.responder = lambda flux: []
    resp = test_client.post("/download", data={
        "start_utc": "2026-08-01T00:00:00Z",
        "stop_utc": "2026-08-01T01:00:00Z",
        "timezone": "UTC",
        "interval": "banana",
        "measurements": ["SOG"],
    })
    assert resp.status_code == 200
    assert "aggregateWindow(every: 10s" in fake_client.query_api_.queries[0]


def test_download_unknown_timezone_falls_back_to_utc(test_client, fake_client, utc_timestamp):
    fake_client.query_api_.responder = lambda flux: [
        type("T", (), {"records": [
            type("R", (), {
                "get_time": lambda self: utc_timestamp(2026, 8, 1, 12, 0, 0),
                "get_value": lambda self: 10.0,
            })(),
        ]})()
    ]
    resp = test_client.post("/download", data={
        "start_utc": "2026-08-01T00:00:00Z",
        "stop_utc": "2026-08-02T00:00:00Z",
        "timezone": "Mars/OlympusMons",
        "interval": "1s",
        "measurements": ["SOG"],
    })
    assert resp.status_code == 200
    # Unknown zone -> UTC timestamps unchanged
    assert "2026-08-01 12:00:00" in resp.get_data(as_text=True)


def test_download_orders_columns_by_group_order(test_client, fake_client, utc_timestamp):
    """Even when the form posts measurements in a different order, CSV columns
    follow MEASUREMENT_GROUPS order (LAT before SOG)."""
    fake_client.query_api_.responder = lambda flux: []
    resp = test_client.post("/download", data={
        "start_utc": "2026-08-01T00:00:00Z",
        "stop_utc": "2026-08-01T01:00:00Z",
        "timezone": "UTC",
        "interval": "1s",
        "measurements": ["SOG", "LAT"],
    })
    body = resp.get_data(as_text=True)
    assert body.startswith("timestamp,LAT,SOG")


def test_download_unknown_abbrev_ignored(test_client, fake_client):
    fake_client.query_api_.responder = lambda flux: []
    resp = test_client.post("/download", data={
        "start_utc": "2026-08-01T00:00:00Z",
        "stop_utc": "2026-08-01T01:00:00Z",
        "timezone": "UTC",
        "interval": "1s",
        "measurements": ["NOPE", "SOG"],
    })
    assert resp.status_code == 200
    assert resp.get_data(as_text=True).startswith("timestamp,SOG")


def test_download_filename_uses_local_times(test_client, fake_client, utc_timestamp):
    fake_client.query_api_.responder = lambda flux: []
    resp = test_client.post("/download", data={
        "start_utc": "2026-08-01T22:00:00Z",
        "stop_utc": "2026-08-02T01:00:00Z",
        "timezone": "Europe/Warsaw",
        "interval": "1s",
        "measurements": ["SOG"],
    })
    cd = resp.headers["Content-Disposition"]
    # 22:00Z -> 00:00 next day in Warsaw (UTC+2 summer); 01:00Z -> 03:00
    assert "20260802_000000" in cd
    assert "20260802_030000" in cd


def test_download_csv_parses_cleanly(test_client, fake_client, utc_timestamp):
    """The CSV must round-trip through the csv module without errors."""
    import csv
    fake_client.query_api_.responder = lambda flux: [
        type("T", (), {"records": [
            type("R", (), {
                "get_time": lambda self: utc_timestamp(2026, 8, 1, 0, 0, 0),
                "get_value": lambda self: 10.0,
            })(),
        ]})()
    ]
    resp = test_client.post("/download", data={
        "start_utc": "2026-08-01T00:00:00Z",
        "stop_utc": "2026-08-01T01:00:00Z",
        "timezone": "UTC",
        "interval": "1s",
        "measurements": ["SOG", "LAT"],
    })
    rows = list(csv.DictReader(io.StringIO(resp.get_data(as_text=True))))
    assert rows and rows[0]["SOG"] == "19.4384"
