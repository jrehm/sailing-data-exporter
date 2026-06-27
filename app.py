import csv
import io
import os
from collections import OrderedDict
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

# Measurement groups shown in the UI.  Order matters for column order in CSV.
MEASUREMENT_GROUPS = [
    ("Navigation", [
        "navigation.speedOverGround",
        "navigation.headingMagnetic",
        "navigation.headingTrue",
        "navigation.courseOverGroundTrue",
        "navigation.courseOverGroundMagnetic",
        "navigation.rateOfTurn",
        "navigation.position",
    ]),
    ("Attitude", [
        "navigation.attitude.roll",
        "navigation.attitude.pitch",
        "navigation.attitude.yaw",
    ]),
    ("Wind", [
        "environment.wind.speedApparent",
        "environment.wind.angleApparent",
    ]),
    ("Depth", [
        "environment.depth.belowKeel",
    ]),
    ("Racing", [
        "navigation.racing.startTime",
        "navigation.racing.timeToStart",
        "navigation.racing.timeToLine",
        "navigation.racing.timeToBurn",
        "navigation.racing.distanceStartline",
        "navigation.racing.nextLegHeading",
    ]),
]

INTERVAL_OPTIONS = [
    ("1s",  "Raw (1s)"),
    ("5s",  "5 seconds"),
    ("10s", "10 seconds (default)"),
    ("30s", "30 seconds"),
    ("1m",  "1 minute"),
]

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = Flask(__name__)
if os.environ.get("BEHIND_PROXY", "").lower() in ("1", "true", "yes"):
    app.wsgi_app = ProxyFix(app.wsgi_app, x_prefix=1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _local_now_iso() -> str:
    """Return current UTC time formatted for datetime-local input."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")


def _query_measurement(client: InfluxDBClient, measurement: str,
                        start: str, stop: str, interval: str) -> dict:
    """Query a single measurement and return {iso_timestamp: value_str}."""
    if interval == "1s":
        agg = ""
    else:
        agg = f'  |> aggregateWindow(every: {interval}, fn: first, createEmpty: false)\n'

    flux = (
        f'from(bucket: "{INFLUX_BUCKET}")\n'
        f'  |> range(start: {start}, stop: {stop})\n'
        f'  |> filter(fn: (r) => r["_measurement"] == "{measurement}")\n'
        f'  |> filter(fn: (r) => r["_field"] == "value")\n'
        f'{agg}'
        f'  |> keep(columns: ["_time", "_value"])\n'
    )

    api = client.query_api()
    try:
        tables = api.query(flux)
    except Exception:
        return {}

    result = {}
    for table in tables:
        for record in table.records:
            ts = record.get_time().strftime("%Y-%m-%dT%H:%M:%SZ")
            val = record.get_value()
            if ts not in result and val is not None:
                result[ts] = str(val)
    return result


def _build_csv(measurements: list[str], start: str, stop: str,
               interval: str) -> str:
    """Query all selected measurements and produce wide-format CSV."""
    client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    try:
        # {measurement: {timestamp: value}}
        data: dict[str, dict] = {}
        for m in measurements:
            data[m] = _query_measurement(client, m, start, stop, interval)

        # Collect all timestamps in sorted order
        all_ts: set[str] = set()
        for d in data.values():
            all_ts.update(d.keys())
        sorted_ts = sorted(all_ts)

        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=["timestamp"] + measurements,
                                extrasaction="ignore")
        writer.writeheader()
        for ts in sorted_ts:
            row: dict = {"timestamp": ts}
            for m in measurements:
                row[m] = data[m].get(ts, "")
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
        now=_local_now_iso(),
    )


@app.route("/download", methods=["POST"])
def download():
    # --- Parse form ---
    start_raw = request.form.get("start", "").strip()
    stop_raw  = request.form.get("stop",  "").strip()
    interval  = request.form.get("interval", "10s")
    selected  = request.form.getlist("measurements")

    if not start_raw or not stop_raw:
        return "Missing start or stop time.", 400
    if not selected:
        return "No measurements selected.", 400
    if interval not in {k for k, _ in INTERVAL_OPTIONS}:
        interval = "10s"

    # Convert datetime-local (local browser time, assumed UTC here) to RFC3339
    try:
        start_dt = datetime.fromisoformat(start_raw).replace(tzinfo=timezone.utc)
        stop_dt  = datetime.fromisoformat(stop_raw).replace(tzinfo=timezone.utc)
    except ValueError:
        return "Invalid date format.", 400
    if stop_dt <= start_dt:
        return "Stop time must be after start time.", 400

    start_rfc = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    stop_rfc  = stop_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Preserve order from MEASUREMENT_GROUPS
    all_ordered = [m for _, ms in MEASUREMENT_GROUPS for m in ms]
    ordered_sel = [m for m in all_ordered if m in set(selected)]

    csv_data = _build_csv(ordered_sel, start_rfc, stop_rfc, interval)

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
