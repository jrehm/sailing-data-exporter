# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Reference

- **Stack**: Flask + Jinja2 + InfluxDB (`influxdb-client`)
- **Python**: 3.11+
- **Port**: 5002 (default, override with `PORT` env var)
- **Deployment**: systemd service on HALPI2 (HALOS), fronted by Traefik at `/sailing-data/`

## Commands

```bash
make install   # Create venv, install pinned requirements
make run       # Dev server at localhost:5002
make freeze    # Re-pin requirements.txt from the active venv
```

## Architecture

Single-file Flask app (`app.py`) — no blueprints, no ORM. Two routes:

- `GET /` — renders the form (time window, downsample interval, measurement
  checkboxes) from `MEASUREMENT_GROUPS`
- `POST /download` — parses the form, queries InfluxDB per selected
  measurement, assembles a wide-format CSV, returns it as an attachment

### Key data structure: `MEASUREMENT_GROUPS`

Everything about a measurement lives in one tuple in `app.py`:

```python
(label, abbrev, measurement, field, preferred_source, convert, unit)
```

- `measurement`/`field`: the InfluxDB `_measurement`/`_field` to query (mirrors
  the Signal K path, e.g. `navigation.position` / `lat`)
- `preferred_source`: filters to one `source` tag when multiple devices
  publish the same path (e.g. `n2k-can0.10`); `None` takes the first value
  per timestamp with no filter
- `convert`: function applied to the raw float before it's written to CSV —
  either `_scale(factor)` (multiplies and rounds to 4dp) or `_passthrough`
  (no rounding — only used for LAT/LON, since 4dp is ~11m resolution)
- Derived columns (currently only VMC) have `measurement=None` and are
  computed in `_compute_vmc()` from other already-fetched columns instead of
  queried directly. If you add another derived column, follow this pattern:
  add it to `MEASUREMENT_GROUPS` with `measurement=None`, declare its
  dependencies (like `_VMC_DEPS`), and fetch those dependencies automatically
  in `_build_csv()` even if the user didn't select them.

### Adding a new measurement

1. Confirm the Signal K path and its InfluxDB `_measurement`/`_field` names
   (check `signalk-influxdb` plugin config or query InfluxDB directly)
2. Add a tuple to the appropriate group in `MEASUREMENT_GROUPS`
3. Reuse an existing `_scale(...)` conversion or add a new one if it's a new unit
4. No route/template changes needed — the UI and CSV builder both iterate
   `MEASUREMENT_GROUPS` generically

### Versioning

`__version__` in `app.py` is exposed to Jinja via
`app.jinja_env.globals["VERSION"]` and shown in the UI footer. Bump it and
add a `CHANGELOG.md` entry under `[Unreleased]` when making a notable change;
move it under a dated version heading and tag (`git tag -a vX.Y.Z`) at
release time.

## Deployment

`deploy/halos/install.sh` handles venv creation, pinned dependency install
(from `requirements.txt`), the systemd unit, and the Traefik route. After
pushing to `main`, redeploy with:

```bash
ssh halos "cd /home/pi/GitHub/sailing-data-exporter && git pull && sudo systemctl restart sailing-data-exporter"
```
