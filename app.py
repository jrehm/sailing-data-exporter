import csv
import io
import os
from datetime import datetime, timezone

from flask import Flask, Response, render_template, request
from influxdb_client import InfluxDBClient
from werkzeug.middleware.proxy_fix import ProxyFix

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

INFLUX_URL    = os.environ.get("INFLUX_URL",    "http://localhost:8086")
INFLUX_TOKEN  = os.environ.get("INFLUX_TOKEN",  "")
INFLUX_ORG    = os.environ.get("INFLUX_ORG",    "marine")
INFLUX_BUCKET = os.environ.get("INFLUX_BUCKET", "signalk")

PORT = int(os.environ.get("PORT", 5002))

# ---------------------------------------------------------------------------
# Measurement definitions
#
# Each entry: (label, abbreviation, measurement, field, preferred_source)
#
# preferred_source: if set, filter to that source; if None, take first value
#                   per timestamp (all sources for that measurement are the
#                   same physical sensor, e.g. derived-data or single-source).
# field: normally "value"; position uses "lat" and "lon" (handled specially).
# ---------------------------------------------------------------------------

# Special sentinel for position (two columns from one measurement)
_POS = "_POSITION_"

MEASUREMENT_GROUPS = [
    ("Navigation", [
        # (label, abbrev, measurement, field, preferred_source)
        ("Speed Over Ground",         "SOG",  "navigation.speedOverGround",         "value", "n2k-can0.10"),
        ("Course Over Ground (True)", "COGt", "navigation.courseOverGroundTrue",    "value", "n2k-can0.10"),
        ("Heading Magnetic",          "HDG",  "navigation.headingMagnetic",         "value", "ws.SensESP.XX"),
        ("Heading True",              "HDGt", "navigation.headingTrue",             "value", None),
        ("Rate of Turn",              "ROT",  "navigation.rateOfTurn",              "value", "ws.SensESP.XX"),
        ("Latitude",                  "LAT",  "navigation.position",                "lat",   "n2k-can0.10"),
        ("Longitude",                 "LON",  "navigation.position",                "lon",   "n2k-can0.10"),
        ("Magnetic Variation",        "VAR",  "navigation.magneticVariation",       "value", "derived-data"),
        ("Leeway Angle",              "LEE",  "navigation.leewayAngle",             "value", None),
    ]),
    ("Attitude", [
        ("Roll",  "ROLL",  "navigation.attitude.roll",  "value", "ws.SensESP.XX"),
        ("Pitch", "PITCH", "navigation.attitude.pitch", "value", "ws.SensESP.XX"),
        ("Yaw",   "YAW",   "navigation.attitude.yaw",   "value", "ws.SensESP.XX"),
    ]),
    ("Wind", [
        ("Apparent Wind Speed", "AWS", "environment.wind.speedApparent", "value", "n2k-can0.2"),
        ("Apparent Wind Angle", "AWA", "environment.wind.angleApparent", "value", "n2k-can0.2"),
    ]),
    ("Depth", [
        ("Depth Below Keel", "DBK", "environment.depth.belowKeel", "value", None),
    ]),
    ("Course / VMG", [
        ("VMG to Waypoint",    "VMG", "navigation.course.calcValues.velocityMadeGood", "value", None),
        ("Cross-Track Error",  "XTE", "navigation.course.calcValues.crossTrackError",  "value", None),
    ]),
    ("Racing", [
        ("Time to Start",        "TTS",  "navigation.racing.timeToStart",        "value", None),
        ("Time to Line",         "TTL",  "navigation.racing.timeToLine",         "value", None),
        ("Time to Burn",         "TTB",  "navigation.racing.timeToBurn",         "value", None),
        ("Distance to Line",     "DSL",  "navigation.racing.distanceStartline",  "value", None),
        ("Next Leg Heading",     "NLH",  "navigation.racing.nextLegHeading",     "value", None),
        ("Start Time",           "STA",  "navigation.racing.startTime",          "value", None),
    ]),
]

INTERVAL_OPTIONS = [
    ("1s",  "Raw (1s)"),
    ("5s",  "5 seconds"),
    ("10s", "10 seconds (default)"),
    ("30s", "30 seconds"),
    ("1m",  "1 minute"),
]

# Build flat lookup: abbrev → (measurement, field, preferred_source)
_ABBREV_MAP = {
    abbrev: (measurement, field, source)
    for _, entries in MEASUREMENT_GROUPS
    for (_, abbrev, measurement, field, source) in entries
}

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = Flask(__name__)
if os.environ.get("BEHIND_PROXY", "").lower() in ("1", "true", "yes"):
    app.wsgi_app = ProxyFix(app.wsgi_app, x_prefix=1)


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def _query_series(client: InfluxDBClient, measurement: str, field: str,
                  preferred_source: str | None,
                  start: str, stop: str, interval: str) -> dict[str, str]:
    """Query one (measurement, field) pair. Returns {iso_timestamp: value_str}."""

    source_filter = (
        f'  |> filter(fn: (r) => r["source"] == "{preferred_source}")\n'
        if preferred_source else ""
    )
    agg = (
        ""
        if interval == "1s"
        else f'  |> aggregateWindow(every: {interval}, fn: mean, createEmpty: false)\n'
    )

    flux = (
        f'from(bucket: "{INFLUX_BUCKET}")\n'
        f'  |> range(start: {start}, stop: {stop})\n'
        f'  |> filter(fn: (r) => r["_measurement"] == "{measurement}")\n'
        f'  |> filter(fn: (r) => r["_field"] == "{field}")\n'
        f'{source_filter}'
        f'{agg}'
        f'  |> keep(columns: ["_time", "_value"])\n'
    )

    try:
        tables = client.query_api().query(flux)
    except Exception:
        return {}

    result: dict[str, str] = {}
    for table in tables:
        for record in table.records:
            ts = record.get_time().strftime("%Y-%m-%dT%H:%M:%SZ")
            val = record.get_value()
            if ts not in result and val is not None:
                result[ts] = str(val)
    return result


def _build_csv(selected_abbrevs: list[str],
               start: str, stop: str, interval: str) -> str:
    """Query all selected columns and produce wide-format CSV."""

    client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    try:
        data: dict[str, dict[str, str]] = {}  # abbrev → {ts → value}
        for abbrev in selected_abbrevs:
            measurement, field, source = _ABBREV_MAP[abbrev]
            data[abbrev] = _query_series(
                client, measurement, field, source, start, stop, interval
            )

        all_ts = sorted({ts for d in data.values() for ts in d})

        out = io.StringIO()
        writer = csv.DictWriter(
            out,
            fieldnames=["timestamp"] + selected_abbrevs,
            extrasaction="ignore",
        )
        writer.writeheader()
        for ts in all_ts:
            row: dict = {"timestamp": ts}
            for abbrev in selected_abbrevs:
                row[abbrev] = data[abbrev].get(ts, "")
            writer.writerow(row)

        return out.getvalue()
    finally:
        client.close()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")
    return render_template(
        "index.html",
        groups=MEASUREMENT_GROUPS,
        interval_options=INTERVAL_OPTIONS,
        default_interval="10s",
        now=now,
    )


@app.route("/download", methods=["POST"])
def download():
    start_raw = request.form.get("start", "").strip()
    stop_raw  = request.form.get("stop",  "").strip()
    interval  = request.form.get("interval", "10s")
    selected  = request.form.getlist("measurements")  # list of abbrevs

    if not start_raw or not stop_raw:
        return "Missing start or stop time.", 400
    if not selected:
        return "No measurements selected.", 400
    if interval not in {k for k, _ in INTERVAL_OPTIONS}:
        interval = "10s"

    try:
        start_dt = datetime.fromisoformat(start_raw).replace(tzinfo=timezone.utc)
        stop_dt  = datetime.fromisoformat(stop_raw).replace(tzinfo=timezone.utc)
    except ValueError:
        return "Invalid date format.", 400
    if stop_dt <= start_dt:
        return "Stop time must be after start time.", 400

    start_rfc = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    stop_rfc  = stop_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Keep order matching MEASUREMENT_GROUPS
    ordered_abbrevs = [
        abbrev
        for _, entries in MEASUREMENT_GROUPS
        for (_, abbrev, _, _, _) in entries
        if abbrev in set(selected)
    ]

    csv_data = _build_csv(ordered_abbrevs, start_rfc, stop_rfc, interval)

    filename = (
        f"sailing_{start_dt.strftime('%Y%m%d_%H%M')}"
        f"_to_{stop_dt.strftime('%Y%m%d_%H%M')}.csv"
    )
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
