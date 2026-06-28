import csv
import io
import math
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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
# Unit conversion helpers
# ---------------------------------------------------------------------------

_MPS_TO_KTS  = 1.94384
_RAD_TO_DEG  = math.degrees(1)          # 57.2958
_RADS_TO_DEGMIN = _RAD_TO_DEG * 60      # rad/s → °/min
_M_TO_FT     = 3.28084
_M_TO_NM     = 0.000539957


def _scale(factor: float):
    """Return a converter that multiplies by factor, rounded to 4 dp."""
    def fn(v: float) -> float:
        return round(v * factor, 4)
    return fn


def _abs_scale(factor: float):
    """Like _scale but takes absolute value first (for depth below keel)."""
    def fn(v: float) -> float:
        return round(abs(v) * factor, 4)
    return fn


_IDENTITY = _scale(1.0)

# ---------------------------------------------------------------------------
# Measurement definitions
#
# Each entry: (label, abbrev, measurement, field, preferred_source, convert, unit)
#
# preferred_source: filter to this source; None = take first value per timestamp
# field: normally "value"; position uses "lat" and "lon"
# convert: function applied to raw float value before writing to CSV
# unit: displayed in the UI next to the abbreviation
# ---------------------------------------------------------------------------

MEASUREMENT_GROUPS = [
    ("Navigation", [
        ("Speed Over Ground",          "SOG",  "navigation.speedOverGround",         "value", "n2k-can0.10",    _scale(_MPS_TO_KTS),     "kts"),
        ("Course Over Ground (True)",  "COGt", "navigation.courseOverGroundTrue",    "value", "n2k-can0.10",    _scale(_RAD_TO_DEG),     "°"),
        ("Heading True",               "HDGt", "navigation.headingTrue",             "value", None,             _scale(_RAD_TO_DEG),     "°"),
        ("Rate of Turn",               "ROT",  "navigation.rateOfTurn",              "value", "ws.SensESP.XX",  _scale(_RADS_TO_DEGMIN), "°/min"),
        ("Latitude",                   "LAT",  "navigation.position",                "lat",   "n2k-can0.10",    _IDENTITY,               "°"),
        ("Longitude",                  "LON",  "navigation.position",                "lon",   "n2k-can0.10",    _IDENTITY,               "°"),
        ("Leeway Angle",               "LEE",  "navigation.leewayAngle",             "value", None,             _scale(_RAD_TO_DEG),     "°"),
    ]),
    ("Attitude", [
        ("Roll",  "ROLL",  "navigation.attitude.roll",  "value", "ws.SensESP.XX", _scale(_RAD_TO_DEG), "°"),
        ("Pitch", "PITCH", "navigation.attitude.pitch", "value", "ws.SensESP.XX", _scale(_RAD_TO_DEG), "°"),
    ]),
    ("Wind", [
        ("Apparent Wind Speed", "AWS", "environment.wind.speedApparent", "value", "n2k-can0.2", _scale(_MPS_TO_KTS), "kts"),
        ("Apparent Wind Angle", "AWA", "environment.wind.angleApparent", "value", "n2k-can0.2", _scale(_RAD_TO_DEG), "°"),
    ]),
    ("Depth", [
        ("Depth Below Keel", "DBK", "environment.depth.belowKeel", "value", None, _abs_scale(_M_TO_FT), "ft"),
    ]),
    ("Course / VMG", [
        ("VMG to Waypoint",   "VMG", "navigation.course.calcValues.velocityMadeGood", "value", None, _scale(_MPS_TO_KTS), "kts"),
        ("Cross-Track Error", "XTE", "navigation.course.calcValues.crossTrackError",  "value", None, _scale(_M_TO_NM),    "nm"),
    ]),
    ("Racing", [
        ("Time to Start",    "TTS", "navigation.racing.timeToStart",       "value", None, _IDENTITY,             "s"),
        ("Time to Line",     "TTL", "navigation.racing.timeToLine",        "value", None, _IDENTITY,             "s"),
        ("Time to Burn",     "TTB", "navigation.racing.timeToBurn",        "value", None, _IDENTITY,             "s"),
        ("Distance to Line", "DSL", "navigation.racing.distanceStartline", "value", None, _scale(_M_TO_FT),      "ft"),
        ("Next Leg Heading", "NLH", "navigation.racing.nextLegHeading",    "value", None, _scale(_RAD_TO_DEG),   "°"),
        ("Start Time",       "STA", "navigation.racing.startTime",         "value", None, _IDENTITY,             "s"),
    ]),
]

INTERVAL_OPTIONS = [
    ("1s",  "Raw (1s)"),
    ("5s",  "5 seconds"),
    ("10s", "10 seconds (default)"),
    ("30s", "30 seconds"),
    ("1m",  "1 minute"),
]

# Flat lookup: abbrev → (measurement, field, preferred_source, convert)
_ABBREV_MAP = {
    abbrev: (measurement, field, source, convert)
    for _, entries in MEASUREMENT_GROUPS
    for (_, abbrev, measurement, field, source, convert, _unit) in entries
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
                  preferred_source: str | None, convert,
                  start: str, stop: str, interval: str) -> dict[str, str]:
    """Query one (measurement, field) pair. Returns {iso_timestamp: str_value}."""

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
                try:
                    result[ts] = str(convert(float(val)))
                except (TypeError, ValueError):
                    result[ts] = str(val)
    return result


def _build_csv(selected_abbrevs: list[str],
               start: str, stop: str, interval: str,
               tz: ZoneInfo) -> str:
    """Query all selected columns and produce wide-format CSV."""

    client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    try:
        data: dict[str, dict[str, str]] = {}
        for abbrev in selected_abbrevs:
            measurement, field, source, convert = _ABBREV_MAP[abbrev]
            data[abbrev] = _query_series(
                client, measurement, field, source, convert,
                start, stop, interval,
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
            # Convert UTC timestamp string to local time
            utc_dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            local_ts = utc_dt.astimezone(tz).strftime("%Y-%m-%d %H:%M:%S")
            row: dict = {"timestamp": local_ts}
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
    return render_template(
        "index.html",
        groups=MEASUREMENT_GROUPS,
        interval_options=INTERVAL_OPTIONS,
        default_interval="10s",
    )


@app.route("/download", methods=["POST"])
def download():
    start_raw = request.form.get("start_utc", "").strip()
    stop_raw  = request.form.get("stop_utc",  "").strip()
    tz_name   = request.form.get("timezone",  "UTC").strip()
    interval  = request.form.get("interval", "10s")
    selected  = request.form.getlist("measurements")  # list of abbrevs

    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, KeyError):
        tz = timezone.utc

    if not start_raw or not stop_raw:
        return "Missing start or stop time.", 400
    if not selected:
        return "No measurements selected.", 400
    if interval not in {k for k, _ in INTERVAL_OPTIONS}:
        interval = "10s"

    try:
        # JS sends full ISO 8601 with Z suffix — parse directly as UTC
        start_dt = datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
        stop_dt  = datetime.fromisoformat(stop_raw.replace("Z", "+00:00"))
    except ValueError:
        return "Invalid date format.", 400
    if stop_dt <= start_dt:
        return "Stop time must be after start time.", 400

    start_rfc = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    stop_rfc  = stop_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Preserve order from MEASUREMENT_GROUPS
    ordered_abbrevs = [
        abbrev
        for _, entries in MEASUREMENT_GROUPS
        for (_, abbrev, _, _, _, _, _) in entries
        if abbrev in set(selected)
    ]

    csv_data = _build_csv(ordered_abbrevs, start_rfc, stop_rfc, interval, tz)

    local_start = start_dt.astimezone(tz)
    local_stop  = stop_dt.astimezone(tz)
    filename = (
        f"sailing_{local_start.strftime('%Y%m%d_%H%M%S')}"
        f"_to_{local_stop.strftime('%Y%m%d_%H%M%S')}.csv"
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
