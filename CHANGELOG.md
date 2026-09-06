# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `ETEMP` (eCompass die temperature, °C) from
  `environment.inside.ecompass.temperature`, source `SensESP.XX`. Signal K
  publishes temperature in Kelvin and `_scale()` is multiply-only, so this
  adds a `_kelvin_to_c()` converter. Without this column the thermal-offset
  (TCO) model cannot be applied to or validated against sailing data from the
  CSV alone -- it required a separate InfluxDB join, which is why the open
  "apply the TCO coefficients to the sailing data" task had no clean path.
- `SATS` and `HDOP` (`navigation.gnss.satellites`,
  `navigation.gnss.horizontalDilution`). These make GPS fix quality visible
  in the export so the cleaning pipeline can filter degraded rows on the
  actual cause rather than the bit-identical-to-previous heuristic. Relevant
  now: with the antenna obstruction active, 26.4% of underway samples on
  08-26 and 17.7% on 09-02 have a frozen velocity solution.
- `HDGmT` (Heading Magnetic, eCompass TC) in the Magnetic Calibration group,
  reading `sensors.ecompass.headingMagneticTC` -- the thermally-corrected
  eCompass heading introduced by the Phase 2a firmware, publishing since
  2026-09-04 17:04 UTC. Without the column, exporting any post-flash session
  returns only the uncorrected heading.

Column availability by date, for anyone reading old exports:
  - before 2026-08-19 20:00 EDT : HDGmE, HDGmF, HDGmT all empty
  - 2026-08-19 20:00 EDT onward : HDGmE, HDGmF populated
  - 2026-09-04 17:04 UTC onward : HDGmT populated
  - ETEMP, SATS, HDOP populated for the full history of the bucket
    (from 2026-07-28)

### Changed
- Moved `HDGmE` and `HDGmF` (magnetic heading, eCompass/fluxgate) from the
  Navigation group to Magnetic Calibration -- they're mag-cal diagnostics
  inputs, not general navigation data.

### Fixed
- `HDGmE`/`HDGmF` were coming back empty in every CSV export: both still
  queried raw `navigation.headingMagnetic` filtered by source, but that path
  got a `priorityOverrides` entry in SignalK on 2026-08-19, and once a path
  has an active override, InfluxDB only records the winning source's deltas
  -- the losing source (eCompass or fluxgate, whichever isn't primary at any
  given moment) silently stopped reaching InfluxDB at all. Repointed both
  columns at `sensors.ecompass.headingMagnetic` / `sensors.fluxgate.headingMagnetic`,
  the dedicated `signalk-path-mapper` duplicate paths that exist specifically
  to work around this (single source each, so no source filter needed).

## [0.6.0] - 2026-08-19

### Added
- Two explicit-source magnetic heading columns, `HDGmE` (eCompass, source
  `SensESP.XX`) and `HDGmF` (fluxgate, source `n2k-can0.9`), both from
  `navigation.headingMagnetic`. Added ahead of switching the boat's live
  heading source (Signal K priority) from the eCompass to the newly-added
  N2K fluxgate: `HDGt` (Heading True) has no source filter, so it silently
  follows whatever Signal K currently prioritizes -- once the fluxgate
  becomes primary, `HDGt` alone would no longer capture the eCompass's
  readings, breaking the ongoing eCompass evaluation without any error.
  These two columns pin to each device explicitly so both keep getting
  captured by every export regardless of which one is live/primary.

## [0.5.0] - 2026-08-13

### Added
- New "Magnetic Calibration" group, sourcing the `orientation.calibration.*`
  paths added by yesterday's Morticia-eCompass firmware update: MFIT/MFITT
  (in-use/trial fit error, %), MSOLV (solver algorithm order, 0-10), MNOIS
  (magnetic noise), MAGB/MAGBT (in-use/trial field magnitude, µT), MINCL
  (field inclination, converted rad→°), MCALF/MCALH (fit-error and heading
  shift from the last auto-accepted calibration event). Units/thresholds
  pulled directly from the firmware's own `SKMetadata` in
  Morticia-eCompass/src/main.cpp rather than inferred from magnitudes.
  Verified all 9 paths are logged to InfluxDB before adding.

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
