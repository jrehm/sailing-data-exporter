# Sailing Data Exporter

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Version](https://img.shields.io/badge/version-0.2.0-orange.svg)](CHANGELOG.md)

A small Flask app for pulling a time window of Signal K data out of InfluxDB
and downloading it as a CSV — for post-race analysis, polar generation, or
just checking a track in a spreadsheet.

## Features

- Pick a start/stop time (local time, converted to UTC under the hood)
- Choose a downsample interval (raw 1s up to 1 minute)
- Check off individual measurements, grouped by category (Location,
  Navigation, Attitude, Wind, Course/VMG, Racing)
- Derived columns (e.g. VMC) computed from other selected columns
- CSV filename includes the local time window it covers
- Full GPS precision on Latitude/Longitude (no lossy rounding)

## Requirements

- Python 3.11+
- A running InfluxDB 2.x instance with Signal K data already being logged
  into it (this app only reads — it doesn't write anything back)

## Quick Start

```bash
git clone https://github.com/jrehm/sailing-data-exporter.git
cd sailing-data-exporter
make install

cp deploy/halos/sailing-data-exporter.env.example .env
# edit .env with your InfluxDB URL/token/org/bucket

set -a; source .env; set +a   # app.py reads os.environ directly, no dotenv loader
make run
```

Visit `http://localhost:5002`.

## Configuration

Environment variables (see `deploy/halos/sailing-data-exporter.env.example`):

| Variable | Default | Description |
|---|---|---|
| `INFLUX_URL` | `http://localhost:8086` | InfluxDB base URL |
| `INFLUX_TOKEN` | *(none)* | InfluxDB API token |
| `INFLUX_ORG` | `marine` | InfluxDB org |
| `INFLUX_BUCKET` | `signalk` | InfluxDB bucket to query |
| `BEHIND_PROXY` | *(unset)* | Set `true` if running behind a reverse proxy (adds `ProxyFix`) |
| `PORT` | `5002` | Port for the Flask dev server |

## Measurements

Each measurement is queried from InfluxDB by `(measurement, field)`, optionally
filtered to a specific `source` tag when more than one device publishes the
same path. Values are converted (unit scaling) before being written to CSV.

| Group | Abbrev | Label | Unit |
|---|---|---|---|
| Location | LAT | Latitude | ° (full precision) |
| Location | LON | Longitude | ° (full precision) |
| Location | DBS | Depth Below Surface | ft |
| Navigation | SOG | Speed Over Ground | kts |
| Navigation | COGt | Course Over Ground (True) | ° |
| Navigation | HDGt | Heading True | ° |
| Navigation | ROT | Rate of Turn | °/min |
| Navigation | LEE | Leeway Angle | ° |
| Attitude | ROLL | Roll | ° |
| Attitude | PITCH | Pitch | ° |
| Wind | AWS | Apparent Wind Speed | kts |
| Wind | AWA | Apparent Wind Angle | ° |
| Wind | TWS | True Wind Speed | kts |
| Wind | TWA | True Wind Angle | ° |
| Wind | TWD | True Wind Direction | ° |
| Wind | MROT | Mast Rotation | ° |
| Performance | VMG | Velocity Made Good (true wind) | kts |
| Performance | VMC | VMC (closing speed on mark) | kts |
| Performance | BRG | Bearing to Mark | ° |
| Performance | DTG | Distance to Mark | nm |
| Performance | XTE | Cross-Track Error | nm |
| Racing | TTS | Time to Start | s |
| Racing | TTL | Time to Line | s |
| Racing | TTB | Time to Burn | s |
| Racing | DSL | Distance to Line | ft |
| Racing | NLH | Next Leg Heading | ° |
| Racing | STA | Start Time | s |

**VMG vs. VMC** — these are often confused, including by Signal K's own path
naming. VMG (Velocity Made Good) is boat speed relative to the *true wind*
(cos of true wind angle) — used to judge upwind/downwind efficiency against
polar targets. VMC (Velocity Made good on Course) is boat speed relative to
a *waypoint bearing* (cos of COG − BRG) — closing speed toward a mark.
Signal K's `navigation.course.calcValues.velocityMadeGood` path is actually
VMC despite the name; this app sources VMG separately from
`performance.velocityMadeGood` (published by signalk-polar-performance-plugin)
to keep the two straight. VMC (along with BRG/DTG/XTE) only has values when
a destination/course is active via the Course API; VMG only has values when
the polar-performance plugin has a polar configured.

Adding a new measurement is a one-line addition to `MEASUREMENT_GROUPS` in
`app.py` — no other code changes needed unless it requires a new unit
conversion.

## Deployment (HALPI2 / HALOS)

This runs as a systemd service on HALPI2, fronted by Traefik.

```bash
git clone https://github.com/jrehm/sailing-data-exporter.git /home/pi/GitHub/sailing-data-exporter
cd /home/pi/GitHub/sailing-data-exporter
cp deploy/halos/sailing-data-exporter.env.example deploy/halos/sailing-data-exporter.env
# edit deploy/halos/sailing-data-exporter.env with real InfluxDB token
./deploy/halos/install.sh
```

`install.sh` creates the venv, installs pinned dependencies, installs the
systemd unit, and wires up the Traefik route. The app is then reachable at
`https://halos.local/sailing-data/`.

To deploy a new version after pushing to `main`:

```bash
ssh halos "cd /home/pi/GitHub/sailing-data-exporter && git pull && sudo systemctl restart sailing-data-exporter"
```

## Project Structure

```
sailing-data-exporter/
├── app.py                                        # Flask app: routes, measurement defs, CSV builder
├── templates/
│   └── index.html                                # Single-page UI (time window, checkboxes, download)
├── deploy/halos/
│   ├── install.sh                                 # One-shot install on HALPI2
│   ├── sailing-data-exporter.service               # systemd unit
│   └── sailing-data-exporter.env.example           # Env var template
├── requirements.txt
├── Makefile
├── CHANGELOG.md
└── CLAUDE.md                                       # AI development context
```

## Versioning

This project follows [Semantic Versioning](https://semver.org/). See
[CHANGELOG.md](CHANGELOG.md) for release history. The current version is
shown in the footer of the app itself.

## License

MIT License - See [LICENSE](LICENSE) file for details.
