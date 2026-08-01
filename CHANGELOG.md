# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- README.md (setup, configuration, measurement reference, deployment, project structure)
- CLAUDE.md (AI development context, matching convention used across other repos)
- Makefile (`install`, `run`, `freeze` targets)
- LICENSE (MIT)

### Changed
- Pinned `requirements.txt` to versions currently deployed on HALOS
- `deploy/halos/install.sh` now installs from `requirements.txt` instead of a
  hardcoded package list, so deployed and documented versions can't drift
- Expanded `.gitignore` with standard Python/editor/OS entries
- README license note updated from "not licensed" to MIT, now that LICENSE exists

## [0.1.0] - 2026-08-01

### Added
- Initial MVP: time window picker, per-measurement checkboxes, CSV download
- TWS, TWA, TWD true wind columns
- BRG (bearing to mark, °) and DTG (distance to mark, nm) columns
- VMC (velocity made on course) as a derived column
- Mast rotation added to the Wind group
- Version string in the UI footer, and this changelog

### Changed
- Location group now listed first; `DBK` renamed to `DBS` (Depth Below Surface)
- CSV timestamps use the browser's local timezone instead of UTC
- Download filename includes local timezone and seconds
- Datetime pickers include seconds (`step=1`)
- Wind columns point at the AdvancedWind source instead of a stale `GND10` tag
- Roll/pitch columns point at `signalk-attitude-calibrator` instead of a stale source
- ROT column points at `SensESP.XX` instead of a stale `ws.SensESP.XX` source
- Dropped magnetic heading/variation and YAW in favor of true-reference equivalents
- Latitude/Longitude no longer rounded to 4 decimal places (~11 m resolution);
  now exported at full GPS precision

### Fixed
- Removed a committed `.env` file containing a live InfluxDB token from version control
