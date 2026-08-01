# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.0] - 2026-08-01

### Added
- Nearly the entire signalk-polar-performance-plugin output as new Performance
  columns: TGTA, TGTS, TVMG (target angle/speed/VMG), PSPD, PSR, PVMG, PVMGR
  (polar speed/VMG and their ratios to actual), BTA, BTVMG, GBA, GBVMG (beat
  and gybe angle plus their VMG), VMAX, VMAXA (max speed and its angle), OWA
  (optimum wind angle), TACK (true tack angle). Checked by default, same as
  every other measurement — uncheck to exclude.
- Deliberately excluded `performance.velocityMadeGoodToWaypoint` — it's the
  same waypoint-closing-speed concept as the existing VMC column (just the
  newer schema alias for what `navigation.course.calcValues.velocityMadeGood`
  already publishes), so adding it would just be a duplicate column.

## [0.3.0] - 2026-08-01

### Added
- `/changelog` route, serving `CHANGELOG.md` locally so it's readable with
  no internet access underway
- Version number in the UI footer is now a link to the changelog

### Changed
- Merged the standalone "Attitude" group (Roll, Pitch) into Navigation —
  Location is earth-frame position (lat/lon/depth), while Roll/Pitch are
  vessel orientation, the same category as Heading and Rate of Turn
- Moved BRG, DTG, XTE from Performance into Navigation, leaving Performance
  as just the two velocity-made-good columns (VMG, VMC)

## [0.2.0] - 2026-08-01

### Added
- Genuine VMG (true wind-relative velocity made good) column, sourced from
  `performance.velocityMadeGood` (published by signalk-polar-performance-plugin)
- LICENSE file (MIT)
- README.md (setup, configuration, measurement reference, deployment, project structure)
- CLAUDE.md (AI development context, matching convention used across other repos)
- Makefile (`install`, `run`, `freeze` targets)

### Changed
- Renamed the "Course / VMG" group to "Performance"
- Fixed a mislabeled column: what was called "VMG to Waypoint" was actually
  pulling `navigation.course.calcValues.velocityMadeGood`, which the
  `course-provider` plugin defines as waypoint-closing speed — i.e. VMC, not
  VMG. Relabeled to "VMC (closing speed on mark)" to match what it actually is.
- Removed the locally-derived VMC calculation (`SOG × cos(COGt − BRG)`) in
  favor of consuming the already-published `navigation.course.calcValues.velocityMadeGood`
  directly — it was quietly diverging from the Signal K course-provider's own
  calculation (rhumbline vs. great-circle bearing handling) and duplicated
  logic the server already provides
- Pinned `requirements.txt` to versions currently deployed on HALOS
- `deploy/halos/install.sh` now installs from `requirements.txt` instead of a
  hardcoded package list, so deployed and documented versions can't drift
- Expanded `.gitignore` with standard Python/editor/OS entries
- README license note updated from "not licensed" to MIT, now that LICENSE exists

### Removed
- `_compute_vmc()` and `_VMC_DEPS` (superseded — see Changed)

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
